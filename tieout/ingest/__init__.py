"""Ingestion: load, map columns, validate, annualise and prepare the ``lines`` frame."""

from tieout.ingest.load import FileLimitError, UnreadableFileError, load_file
from tieout.ingest.mapping import ColumnSuggestion, suggest_mapping
from tieout.ingest.prepare import Prepared, prepare
from tieout.ingest.validate import BlockingValidationError, DataQualityReport

__all__ = [
    "BlockingValidationError",
    "ColumnSuggestion",
    "DataQualityReport",
    "FileLimitError",
    "Prepared",
    "UnreadableFileError",
    "load_file",
    "prepare",
    "suggest_mapping",
]
