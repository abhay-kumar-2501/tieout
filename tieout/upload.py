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
from tieout.ingest.validate import parse_dates
from tieout.normalise.taxonomy import suggest_categories
from tieout.pipeline import (
    CATEGORY_MAP_COLUMNS,
    PipelineInputs,
    read_category_settings,
    run_pipeline,
)
from tieout.reference import load_fx_rates, load_taxonomy
from tieout.results import Results

__all__ = [
    "MAX_BYTES",
    "MAX_ROWS",
    "FilePeek",
    "ParsedOptions",
    "UploadCheck",
    "UploadOptions",
    "detect_period_end",
    "parse_options",
    "category_map_from",
    "apply_category_file",
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
class UploadOptions:
    """The optional files (raw bytes, PRD 3.2) and settings; defaults change nothing."""

    fx: bytes | None = None
    vendor_parents: bytes | None = None
    category_settings: bytes | None = None
    period_end: str | None = None  # "YYYY-MM"; None = the earlier of the files' latest months
    reporting_currency: str = "USD"
    aggregated: bool = False


@dataclass(frozen=True)
class ParsedOptions:
    """:class:`UploadOptions` read and checked: frames ready for the pipeline."""

    fx: pd.DataFrame | None
    vendor_parents: pd.DataFrame | None
    category_settings: pd.DataFrame | None
    period_end: str | None
    reporting_currency: str
    aggregated: bool


def _csv(data: bytes, what: str, required: tuple[str, ...]) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            io.BytesIO(data), dtype=str, keep_default_na=False, encoding_errors="replace"
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"The {what} file could not be read as CSV.") from exc
    frame.columns = pd.Index([str(c).strip().lower() for c in frame.columns])
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(
            f"The {what} file needs the columns {', '.join(required)}; "
            f"missing {', '.join(missing)}."
        )
    return frame


def parse_options(options: UploadOptions) -> ParsedOptions:
    """Read and check the optional inputs; raises ``ValueError`` with a plain message."""
    fx = None
    if options.fx is not None:
        fx = _csv(options.fx, "FX rates", ("currency", "rate"))
        for currency, rate in zip(fx["currency"], fx["rate"], strict=True):
            try:
                ok = float(rate) > 0
            except ValueError:
                ok = False
            if not ok:
                raise ValueError(
                    f"The FX rates file has a rate for {currency} that is not positive."
                )
        fx = fx[["currency", "rate"]].assign(rate=fx["rate"].astype(float))
    parents = None
    if options.vendor_parents is not None:
        parents = _csv(options.vendor_parents, "vendor parents", ("key_type", "key", "parent_name"))
        bad = sorted(set(parents["key_type"].str.strip().str.lower()) - {"name", "tax_id"})
        if bad:
            raise ValueError(
                f"The vendor parents file has key_type values other than name or tax_id: {bad}."
            )
    settings = None
    if options.category_settings is not None:
        settings = _csv(options.category_settings, "category settings", ("l2_code",))
        try:
            read_category_settings(settings)
        except ValueError as exc:
            raise ValueError(f"The category settings file is not valid: {exc}") from exc
    period = options.period_end
    if period is not None:
        try:
            period = str(pd.Period(period, "M"))
        except (ValueError, TypeError) as exc:
            raise ValueError("The period end must be a month such as 2025-12.") from exc
    currency = options.reporting_currency.strip().upper()
    if not (len(currency) == 3 and currency.isalpha()):
        raise ValueError("The reporting currency must be a three-letter code such as USD.")
    if currency != "USD" and fx is None:
        raise ValueError(
            f"The shipped FX rates are in USD. Add an FX rates file with rates into {currency}."
        )
    return ParsedOptions(fx, parents, settings, period, currency, options.aggregated)


def detect_period_end(
    acquirer: bytes, target: bytes, mapping: Mapping[str, Mapping[str, str | None]]
) -> str | None:
    """The default period end: the earlier of the two files' latest ``doc_date`` months."""
    latest = []
    for company, data in zip(COMPANIES, (acquirer, target), strict=True):
        frame = load_file(_source(data, company), company, _clean(mapping.get(company, {})))
        if "doc_date" not in frame:
            return None
        dates = parse_dates(frame["doc_date"]).dropna()
        if dates.empty:
            return None
        latest.append(dates.max().to_period("M"))
    return str(min(latest))


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
    options: UploadOptions | None = None,
) -> UploadCheck:
    """Validate the pair under the column ``mapping`` (``{"acquirer": {...}, "target": {...}}``)."""
    parsed = parse_options(options or UploadOptions())
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
            fx=parsed.fx if parsed.fx is not None else load_fx_rates(),
            taxonomy=taxonomy,
            period_end=parsed.period_end,
            aggregated=parsed.aggregated,
            reporting_currency=parsed.reporting_currency,
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


def apply_category_file(choices: pd.DataFrame, data: bytes) -> tuple[pd.DataFrame, int, int]:
    """Apply a ``category_map.csv`` (PRD 3.2) to the category choices.

    Rows are matched on company and native category (trimmed, case-insensitive).
    Returns the updated choices, how many categories were set, and how many file
    rows were skipped (no such category, or an ``l2_code`` not in the taxonomy).
    Raises ``ValueError`` when the file lacks a required column.
    """
    try:
        file = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ValueError("The category map could not be read as CSV.") from exc
    missing = [c for c in CATEGORY_MAP_COLUMNS if c not in file.columns]
    if missing:
        raise ValueError(f"The category map needs the columns {', '.join(CATEGORY_MAP_COLUMNS)}.")
    known = set(load_taxonomy()["l2_code"])

    def key(company: pd.Series, label: pd.Series) -> pd.Series:
        return (
            company.astype(str).str.strip().str.lower()
            + "|"
            + label.astype(str).str.strip().str.casefold()
        )

    wanted = dict(
        zip(
            key(file["company"], file["category_native"]),
            file["l2_code"].str.strip(),
            strict=True,
        )
    )
    out = choices.copy()
    keys = key(out["company"], out["category_native"])
    applied = 0
    for i, k in zip(out.index, keys, strict=True):
        code = wanted.get(k)
        if code in known:
            out.at[i, "l2_code"] = code
            applied += 1
    skipped = len(file) - sum(1 for k in set(keys) if wanted.get(k) in known)
    return out, applied, max(skipped, 0)


def run_upload(
    acquirer: bytes,
    target: bytes,
    mapping: Mapping[str, Mapping[str, str | None]],
    category_map: pd.DataFrame,
    *,
    options: UploadOptions | None = None,
    names: Mapping[str, str] | None = None,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Results:
    """Run the full pipeline on the confirmed mappings; raises ``BlockingValidationError``.

    ``names`` gives each file's display name (kept as ``source_file`` on the lines).
    """
    given = names or {}
    parsed = parse_options(options or UploadOptions())
    inputs = PipelineInputs(
        acquirer=_source(acquirer, given.get("acquirer", "acquirer")),  # type: ignore[arg-type]
        target=_source(target, given.get("target", "target")),  # type: ignore[arg-type]
        mapping={c: _clean(mapping.get(c, {})) for c in COMPANIES},
        category_map=category_map_from(category_map),
        fx=parsed.fx,
        vendor_parents=parsed.vendor_parents,
        category_settings=parsed.category_settings,
        period_end=parsed.period_end,
        aggregated=parsed.aggregated,
        reporting_currency=parsed.reporting_currency,
        scenario="custom",
    )
    return run_pipeline(inputs, progress=progress)
