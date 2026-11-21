"""Read a purchasing file (CSV or XLSX) into the raw PRD 3.1 frame.

Everything is read as text; typing happens in validation. File names and
contents are never logged and nothing is written to disk.
"""

from __future__ import annotations

import io
import re
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any

import numpy as np
import pandas as pd

from tieout.ingest.schema import COLUMNS, COMPANIES, MAX_BYTES, MAX_ROWS

__all__ = ["FileLimitError", "UnreadableFileError", "load_file"]

Source = str | Path | IO[bytes] | IO[str]

_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"
_DELIMITERS = (",", ";", "\t", "|")


class FileLimitError(ValueError):
    """The file exceeds the row or size limit (PRD 2.3)."""


class UnreadableFileError(ValueError):
    """The file could not be read as CSV or XLSX."""


def load_file(
    path_or_buffer: Source,
    company: str,
    mapping: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Load one company's file as text with the load-time columns added.

    ``mapping`` maps the file's own header to a PRD 3.1 field name. Headers not
    in the mapping are matched to the schema after lower-casing and replacing
    non-alphanumerics with underscores; columns that are not in the schema are
    dropped. Blank cells become ``None`` and fully blank rows are dropped.
    ``source_row`` is the 1-based file row, header = row 1.
    """
    if company not in COMPANIES:
        raise ValueError(f"company must be one of {COMPANIES}")
    data, name = _read_bytes(path_or_buffer)
    if data.startswith(_XLSX_MAGIC):
        raw = _read_xlsx(data)
    elif data.startswith(_XLS_MAGIC):
        raise UnreadableFileError("Legacy .xls files are not supported; save the file as .xlsx.")
    else:
        raw = _read_csv(data)
    if len(raw) > MAX_ROWS:
        raise FileLimitError(f"The file has more than {MAX_ROWS:,} rows, which is the limit.")

    frame = _select_columns(raw, mapping)
    frame.insert(0, "source_row", np.arange(len(frame), dtype="int64") + 2)
    for column in COLUMNS:
        if column in frame:
            frame[column] = _blank_to_none(frame[column])
    present = [c for c in COLUMNS if c in frame]
    blank = frame[present].isna().all(axis=1) if present else pd.Series(True, index=frame.index)
    frame = frame.loc[~blank].reset_index(drop=True)
    frame["company"] = company
    frame["source_file"] = name
    frame["line_id"] = company + ":" + frame["source_row"].astype(str)
    return frame[[*present, "company", "source_file", "source_row", "line_id"]]


def _read_bytes(source: Source) -> tuple[bytes, str]:
    if isinstance(source, str | Path):
        path = Path(source)
        if path.stat().st_size > MAX_BYTES:
            raise FileLimitError(f"The file is larger than {MAX_BYTES // 2**20} MB, the limit.")
        return path.read_bytes(), path.name
    content: Any = source.read()
    if isinstance(content, str):
        content = content.encode("utf-8")
    if len(content) > MAX_BYTES:
        raise FileLimitError(f"The file is larger than {MAX_BYTES // 2**20} MB, the limit.")
    name = getattr(source, "name", None)
    return bytes(content), Path(str(name)).name if name else "upload"


def _read_csv(data: bytes) -> pd.DataFrame:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    header = text.split("\n", 1)[0]
    sep = max(_DELIMITERS, key=lambda d: (header.count(d), d == ","))
    try:
        return pd.read_csv(
            io.StringIO(text),
            sep=sep,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            skip_blank_lines=False,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise UnreadableFileError("The file could not be read as CSV.") from exc


def _read_xlsx(data: bytes) -> pd.DataFrame:
    import openpyxl

    try:
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        max_row = book.worksheets[0].max_row
        book.close()
        if max_row is not None and max_row > MAX_ROWS + 1:
            raise FileLimitError(f"The file has more than {MAX_ROWS:,} rows, which is the limit.")
        return pd.read_excel(
            io.BytesIO(data),
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            engine="openpyxl",
        )
    except FileLimitError:
        raise
    except Exception as exc:  # openpyxl raises many types for corrupt files
        raise UnreadableFileError("The file could not be read as XLSX.") from exc


def _normalise_header(header: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(header).strip().lower()).strip("_")


def _select_columns(raw: pd.DataFrame, mapping: Mapping[str, str] | None) -> pd.DataFrame:
    headers = [str(c).strip() for c in raw.columns]
    clean = {str(k).strip(): v for k, v in (mapping or {}).items()}
    unknown = sorted(set(clean) - set(headers))
    if unknown:
        raise ValueError(f"The mapping refers to columns that are not in the file: {unknown}")
    bad = sorted({v for v in clean.values() if v not in COLUMNS})
    if bad:
        raise ValueError(f"The mapping targets are not schema fields: {bad}")
    positions: list[int] = []
    targets: list[str] = []
    for i, header in enumerate(headers):
        guess = _normalise_header(header)
        target = clean.get(header) or (guess if guess in COLUMNS else None)
        if target is not None:
            positions.append(i)
            targets.append(target)
    duplicated = sorted({t for t in targets if targets.count(t) > 1})
    if duplicated:
        raise ValueError(f"More than one column maps to the same field: {duplicated}")
    frame = raw.iloc[:, positions].copy()
    frame.columns = pd.Index(targets)
    return frame


def _blank_to_none(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    out = text.astype(object)
    out[(text == "").fillna(True).to_numpy(dtype=bool)] = None
    return out
