"""Validation, type parsing, FX conversion and annualisation (PRD 3.3).

The flow is split so that blocking decisions come before any scaling:

1. :func:`parse_file` types one file and flags problem rows (no amounts yet).
2. The orchestrator in :mod:`tieout.ingest.prepare` decides whether a file is
   blocked, resolves the window, and calls :func:`add_parse_findings`,
   :func:`build_lines` and :func:`check_lines` with the scaling factor.

Dollar values in findings are annualised amounts in the reporting currency,
as absolute values. Pandera holds the declarative parts of the schema; the 1%
rule and dollar values are plain code.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pandera.pandas as pa

from tieout.ingest.schema import (
    COLUMNS,
    DATE_COLUMNS,
    NUMBER_COLUMNS,
    TEXT_COLUMNS,
    required_columns,
)
from tieout.normalise.taxonomy import none_for_missing

__all__ = [
    "DQ_COLUMNS",
    "BlockingValidationError",
    "DataQualityReport",
    "ParsedFile",
    "ReportBuilder",
    "add_parse_findings",
    "build_lines",
    "check_lines",
    "exceeds_blocking_share",
    "normalise_fx",
    "parse_dates",
    "parse_file",
    "parse_numbers",
]

DQ_COLUMNS = ("company", "rule", "severity", "rows", "amount", "message", "fix")
_SEVERITY_RANK = {"blocking": 0, "warning": 1, "info": 2}
_AFFECTED_COLUMNS = ["company", "rule", "source_row", "line_id"]
_IGNORED_HELPERS = ("_fx", "_bad_date", "_bad_number", "_bad_currency", "_fx_missing")

BLOCKING_SHARE = 0.01
MISMATCH_FLOOR = 0.01
MISMATCH_SHARE = 0.01

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataQualityReport:
    """The ``data_quality`` frame plus the rows behind each finding."""

    frame: pd.DataFrame
    affected: pd.DataFrame

    @property
    def blocking(self) -> bool:
        return bool((self.frame["severity"] == "blocking").any())

    def rows_for(self, rule: str, company: str | None = None) -> pd.DataFrame:
        """The affected rows (``company``, ``rule``, ``source_row``, ``line_id``) for a rule."""
        return affected_rows(self.affected, rule, company)


def affected_rows(affected: pd.DataFrame, rule: str, company: str | None = None) -> pd.DataFrame:
    """Filter an ``affected`` frame to one rule, optionally one company."""
    mask = affected["rule"] == rule
    if company is not None:
        mask &= affected["company"] == company
    return affected.loc[mask].sort_values(["company", "source_row"], kind="stable")


class BlockingValidationError(Exception):
    """Validation found blocking errors; ``report`` carries the full report."""

    def __init__(self, report: DataQualityReport) -> None:
        self.report = report
        blocking = report.frame[report.frame["severity"] == "blocking"]
        lines = [f"{r.company}: {r.message}" for r in blocking.itertuples()]
        super().__init__("Blocking validation errors:\n" + "\n".join(lines))


class ReportBuilder:
    """Collects findings and the rows behind them."""

    def __init__(self) -> None:
        self._rows: list[dict[str, object]] = []
        self._affected: list[pd.DataFrame] = []

    def add(
        self,
        company: str,
        rule: str,
        severity: str,
        message: str,
        fix: str,
        *,
        affected: pd.DataFrame | None = None,
        rows: int | None = None,
        amount: float = 0.0,
    ) -> None:
        count = len(affected) if affected is not None else (rows or 0)
        self._rows.append(
            {
                "company": company,
                "rule": rule,
                "severity": severity,
                "rows": int(count),
                "amount": float(amount),
                "message": message,
                "fix": fix,
            }
        )
        if affected is not None and len(affected):
            part = affected[["company", "source_row", "line_id"]].copy()
            part.insert(1, "rule", rule)
            self._affected.append(part[_AFFECTED_COLUMNS])

    def build(self) -> DataQualityReport:
        frame = pd.DataFrame(self._rows, columns=list(DQ_COLUMNS))
        frame["_rank"] = frame["severity"].map(_SEVERITY_RANK)
        frame = (
            frame.sort_values(["_rank", "company", "rule"], kind="stable")
            .drop(columns="_rank")
            .reset_index(drop=True)
        )
        affected = (
            pd.concat(self._affected, ignore_index=True)
            if self._affected
            else pd.DataFrame(columns=_AFFECTED_COLUMNS)
        )
        affected = affected.sort_values(["company", "rule", "source_row"], kind="stable")
        return DataQualityReport(frame, affected.reset_index(drop=True))


def exceeds_blocking_share(affected: int, total: int) -> bool:
    """True when ``affected`` is more than 1% of ``total`` (exactly 1% is not)."""
    return affected * 100 > total


# ---------------------------------------------------------------------------
# Type parsing
# ---------------------------------------------------------------------------

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


def _text(series: pd.Series) -> pd.Series:
    """Stripped strings with blanks as ``None`` (object dtype)."""
    text = series.astype("string").str.strip()
    out = text.astype(object)
    out[(text == "").fillna(True).to_numpy(dtype=bool)] = None
    return out


def parse_numbers(series: pd.Series) -> pd.Series:
    """Parse numbers to float; blank and unparseable values become NaN.

    Accepts thousands commas, spaces, a leading currency symbol, parentheses or
    a trailing minus for negatives. European decimal commas are not supported.
    """
    text = series.astype("string").str.strip()
    negative = text.str.match(r"^\(.*\)$").fillna(False).astype(bool)
    trailing = text.str.match(r"^[^-]+-$").fillna(False).astype(bool)
    cleaned = text.str.replace(r"[()\s$€£,_']", "", regex=True).str.rstrip("-")
    values = pd.to_numeric(cleaned.astype(object).where(cleaned.notna(), None), errors="coerce")
    out = values.to_numpy(dtype="float64", na_value=np.nan)
    out = np.where(negative.to_numpy() | trailing.to_numpy(), -out, out)
    out[~np.isfinite(out)] = np.nan
    return pd.Series(out, index=series.index, dtype="float64")


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse dates to ``datetime64[ns]``; blank and unparseable values become NaT.

    Accepted: ``YYYY-MM-DD`` (also ``/`` or ``.``, with an optional time),
    ``YYYYMMDD``, ``MM/DD/YYYY`` (day first when the first part exceeds 12) and
    ``DD-Mon-YYYY``.
    """
    s = series.astype("string").str.strip()
    iso = s.str.extract(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ].*)?$").astype(float)
    compact = s.str.extract(r"^(\d{4})(\d{2})(\d{2})$").astype(float)
    slash = s.str.extract(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[T ].*)?$").astype(float)
    named = s.str.extract(r"^(\d{1,2})[- ]([A-Za-z]{3})[A-Za-z]*[- ,]+(\d{4})$")

    year = iso[0].combine_first(compact[0]).combine_first(slash[2])
    month = iso[1].combine_first(compact[1])
    day = iso[2].combine_first(compact[2])
    first, second = slash[0], slash[1]
    day_first = first > 12
    month = month.combine_first(second.where(day_first, first))
    day = day.combine_first(first.where(day_first, second))
    named_month = named[1].str.lower().map(_MONTHS).astype(float)
    year = year.combine_first(named[2].astype(float))
    month = month.combine_first(named_month)
    day = day.combine_first(named[0].astype(float))

    year = year.where((year >= 1900) & (year <= 2100))
    parts = pd.DataFrame({"year": year, "month": month, "day": day})
    parsed = pd.to_datetime(parts, errors="coerce")
    return parsed.astype("datetime64[ns]")


def normalise_fx(
    fx: Mapping[str, float] | pd.DataFrame, reporting_currency: str
) -> dict[str, float]:
    """FX table as ``{currency: rate}``; the reporting currency is always 1.0."""
    if isinstance(fx, pd.DataFrame):
        pairs = zip(fx["currency"], fx["rate"], strict=True)
    else:
        pairs = fx.items()
    table = {str(c).strip().upper(): float(r) for c, r in pairs}
    for currency, rate in table.items():
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError(f"FX rate for {currency} must be a positive number")
    reporting = reporting_currency.strip().upper()
    if abs(table.setdefault(reporting, 1.0) - 1.0) > 1e-9:
        raise ValueError(f"FX rate for the reporting currency {reporting} must be 1")
    return table


# ---------------------------------------------------------------------------
# Pandera schemas
# ---------------------------------------------------------------------------

_RAW_PRESENCE = {c: pa.Column(required=True) for c in COLUMNS}

TYPED_SCHEMA = pa.DataFrameSchema(
    {
        **{c: pa.Column("datetime64[ns]", nullable=True) for c in DATE_COLUMNS},
        **{c: pa.Column("float64", nullable=True) for c in NUMBER_COLUMNS},
        "currency": pa.Column(object, pa.Check.str_matches(r"^[A-Z]{3}$"), nullable=True),
        "vendor_country": pa.Column(object, pa.Check.str_matches(r"^[A-Z]{2}$"), nullable=True),
        "spend_type": pa.Column(object, pa.Check.isin(["direct", "indirect"]), nullable=True),
        "company": pa.Column(str, pa.Check.isin(["acquirer", "target"])),
        "source_row": pa.Column("int64", pa.Check.ge(2)),
    },
    strict=False,
    coerce=False,
)


def missing_columns(raw: pd.DataFrame, aggregated: bool) -> list[str]:
    """Required columns absent from ``raw`` (``uom`` only when rows carry items)."""
    schema = pa.DataFrameSchema(
        {c: _RAW_PRESENCE[c] for c in required_columns(aggregated)}, strict=False
    )
    missing: set[str] = set()
    try:
        schema.validate(raw, lazy=True)
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases
        missing = set(cases.loc[cases["check"] == "column_in_dataframe", "failure_case"])
    has_item = any(c in raw and raw[c].notna().any() for c in ("item_code", "mpn"))
    if has_item and "uom" not in raw:
        missing.add("uom")
    return [c for c in COLUMNS if c in missing]


# ---------------------------------------------------------------------------
# Parsing one file
# ---------------------------------------------------------------------------


@dataclass
class ParsedFile:
    """One typed file with per-row problem flags (columns prefixed ``_``)."""

    company: str
    frame: pd.DataFrame
    aggregated: bool
    missing_required: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.frame)

    @property
    def excluded(self) -> pd.Series:
        """Rows excluded by a parse, FX or vendor-id rule."""
        f = self.frame
        return (
            f["_bad_date"]
            | f["_bad_number"]
            | f["_bad_currency"]
            | f["_fx_missing"]
            | f["_no_vendor"]
        )

    def blocked(self) -> dict[str, bool]:
        """Which blocking rules fire for this file, by rule group."""
        f, n = self.frame, self.n_rows
        parse_rows = int((f["_bad_date"] | f["_bad_number"] | f["_bad_currency"]).sum())
        return {
            "required_column_missing": bool(self.missing_required),
            "no_rows": n == 0,
            "unparseable": exceeds_blocking_share(parse_rows, n),
            "currency_not_in_fx": exceeds_blocking_share(int(f["_fx_missing"].sum()), n),
            "vendor_id_blank": exceeds_blocking_share(int(f["_no_vendor"].sum()), n),
        }

    @property
    def is_blocked(self) -> bool:
        return any(self.blocked().values())


def parse_file(
    raw: pd.DataFrame, company: str, *, fx: Mapping[str, float], aggregated: bool = False
) -> ParsedFile:
    """Type one raw file and flag problem rows.

    Typed columns are ``datetime64[ns]`` dates and ``float64`` numbers; text
    columns are stripped strings with ``None`` for blanks. ``currency`` is
    upper-cased, ``vendor_country`` is upper-cased with non-ISO values blanked,
    ``uom`` is upper-cased, ``spend_type`` is lower-cased with unknown values
    blanked. Optional columns that cannot be parsed are blanked and flagged.
    """
    n = len(raw)
    frame = pd.DataFrame(index=pd.RangeIndex(n))
    for column in TEXT_COLUMNS:
        frame[column] = _text(raw[column]) if column in raw else pd.Series([None] * n, dtype=object)
    for column in NUMBER_COLUMNS:
        frame[column] = parse_numbers(raw[column]) if column in raw else np.nan
    for column in DATE_COLUMNS:
        frame[column] = (
            parse_dates(raw[column])
            if column in raw
            else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
        )

    never = pd.Series(False, index=frame.index)

    def bad_nonblank(column: str) -> pd.Series:
        if column not in raw:
            return never
        return frame[column].isna() & _text(raw[column]).notna()

    # Required numbers and dates: a blank counts as unparseable. A column that
    # is absent is reported as a missing column instead, never row by row.
    bad_number = never.copy()
    for column in ("quantity", "unit_price", "line_amount"):
        if column in raw:
            bad_number |= frame[column].isna()
    bad_date = frame["doc_date"].isna() if ("doc_date" in raw and not aggregated) else never

    frame["currency"] = frame["currency"].str.upper().astype(object)
    valid_currency = frame["currency"].str.match(r"^[A-Z]{3}$").fillna(False).astype(bool)
    bad_currency = ~valid_currency if "currency" in raw else never
    frame["currency"] = none_for_missing(frame["currency"].where(valid_currency))
    rate = frame["currency"].map(dict(fx)).astype("float64")
    fx_missing = valid_currency & rate.isna()

    country = frame["vendor_country"].str.upper().astype(object)
    frame["vendor_country"] = none_for_missing(
        country.where(country.str.match(r"^[A-Z]{2}$").fillna(False).astype(bool))
    )
    frame["uom"] = frame["uom"].str.upper().astype(object)
    spend = frame["spend_type"].str.lower().astype(object)
    frame["spend_type"] = none_for_missing(spend.where(spend.isin(["direct", "indirect"])))

    # Optional fields that are present but unusable are blanked and flagged.
    bad_optional = never.copy()
    for column in ("payment_date", "contract_end_date", "payment_terms_days", "pack_qty"):
        bad_optional |= bad_nonblank(column)
    nonpositive_pack = (frame["pack_qty"] <= 0).fillna(False)
    negative_terms = (frame["payment_terms_days"] < 0).fillna(False)
    bad_optional |= nonpositive_pack | negative_terms
    frame.loc[nonpositive_pack, "pack_qty"] = np.nan
    frame.loc[negative_terms, "payment_terms_days"] = np.nan
    frame["payment_terms_days"] = frame["payment_terms_days"].round()

    no_vendor = frame["vendor_id"].isna() if "vendor_id" in raw else never

    frame["company"] = company
    frame["source_file"] = raw["source_file"].to_numpy() if "source_file" in raw else "upload"
    rows = raw["source_row"].to_numpy() if "source_row" in raw else np.arange(n) + 2
    frame["source_row"] = rows.astype("int64")
    frame["line_id"] = company + ":" + frame["source_row"].astype(str)

    frame["_fx"] = rate
    frame["_bad_date"] = bad_date.astype(bool)
    frame["_bad_number"] = bad_number.astype(bool)
    frame["_bad_currency"] = bad_currency.astype(bool)
    frame["_fx_missing"] = fx_missing.astype(bool)
    frame["_no_vendor"] = no_vendor.astype(bool)
    frame["_bad_optional"] = bad_optional.astype(bool)

    TYPED_SCHEMA.validate(frame, lazy=True)
    return ParsedFile(company, frame, aggregated, missing_columns(raw, aggregated))


# ---------------------------------------------------------------------------
# Findings from parsing
# ---------------------------------------------------------------------------


def _rows_of(frame: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    return frame.loc[mask, ["company", "source_row", "line_id"]]


def affected_value(frame: pd.DataFrame, mask: pd.Series, scale: float) -> float:
    """Absolute annualised reporting-currency amount of the masked rows."""
    amounts = (frame["line_amount"] * frame["_fx"]).abs()[mask]
    return float(np.nansum(amounts.to_numpy())) * scale


def plural(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"


def add_parse_findings(rb: ReportBuilder, parsed: ParsedFile, scale: float = 1.0) -> None:
    """Add the required-column, parse, FX, vendor-id and optional-field findings."""
    company, f, n = parsed.company, parsed.frame, parsed.n_rows
    if parsed.missing_required:
        rb.add(
            company,
            "required_column_missing",
            "blocking",
            "Required column(s) missing: " + ", ".join(parsed.missing_required) + ".",
            "Map or add the missing columns and upload the file again.",
        )
    if n == 0:
        rb.add(
            company,
            "no_rows",
            "blocking",
            "The file has no purchasing lines.",
            "Upload a file with at least one line.",
        )
        return
    if parsed.missing_required:
        return
    blocked = parsed.blocked()
    severity = "blocking" if blocked["unparseable"] else "warning"
    handling = "Rows are excluded from the analysis and listed."
    groups = (
        ("unparseable_date", f["_bad_date"], "date", "Use dates such as 2024-03-31."),
        (
            "unparseable_number",
            f["_bad_number"],
            "number",
            "Fix quantity, unit_price and line_amount.",
        ),
        (
            "unparseable_currency",
            f["_bad_currency"],
            "currency",
            "Use three-letter ISO 4217 codes.",
        ),
    )
    union = int((f["_bad_date"] | f["_bad_number"] | f["_bad_currency"]).sum())
    for rule, mask, label, fix in groups:
        if mask.any():
            rb.add(
                company,
                rule,
                severity,
                f"{plural(int(mask.sum()), 'row')} with an unparseable or blank {label}. "
                + (
                    f"{union:,} of {n:,} rows are affected in this file (limit 1%)."
                    if severity == "blocking"
                    else handling
                ),
                fix,
                affected=_rows_of(f, mask),
                amount=affected_value(f, mask, scale),
            )
    if f["_fx_missing"].any():
        mask = f["_fx_missing"]
        rb.add(
            company,
            "currency_not_in_fx",
            "blocking" if blocked["currency_not_in_fx"] else "warning",
            f"{plural(int(mask.sum()), 'row')} in a currency missing from the FX table: "
            + ", ".join(sorted(set(f.loc[mask, "currency"]))[:10])
            + ". Rows are excluded and their value is not converted.",
            "Add the currency to the FX rates file.",
            affected=_rows_of(f, mask),
        )
    if f["_no_vendor"].any():
        mask = f["_no_vendor"]
        rb.add(
            company,
            "vendor_id_blank",
            "blocking" if blocked["vendor_id_blank"] else "warning",
            f"{plural(int(mask.sum()), 'row')} without a vendor_id. Rows are excluded and listed.",
            "Fill in vendor_id.",
            affected=_rows_of(f, mask),
            amount=affected_value(f, mask, scale),
        )
    if f["_bad_optional"].any():
        mask = f["_bad_optional"]
        rb.add(
            company,
            "unparseable_optional",
            "warning",
            f"{plural(int(mask.sum()), 'row')} with an unusable optional value (pack_qty, "
            "payment_terms_days, payment_date or contract_end_date). The value is treated as "
            "blank.",
            "Correct the optional columns if they matter.",
            affected=_rows_of(f, mask),
            amount=affected_value(f, mask, scale),
        )


# ---------------------------------------------------------------------------
# Window, annualisation and line checks
# ---------------------------------------------------------------------------


def month_numbers(dates: pd.Series) -> pd.Series:
    """Months since year 0 as floats (NaN for missing dates)."""
    return (dates.dt.year * 12 + dates.dt.month - 1).astype("float64")


def build_lines(parsed: ParsedFile, keep: pd.Series, scale: float) -> pd.DataFrame:
    """Annualised lines for the kept rows of one file."""
    f = parsed.frame.loc[keep].copy()
    f["amount"] = f["line_amount"] * f["_fx"] * scale
    f["unit_price_rc"] = f["unit_price"] * f["_fx"]
    f["quantity_ann"] = f["quantity"] * scale
    return f.drop(columns=list(_IGNORED_HELPERS) + ["_no_vendor", "_bad_optional"])


def check_lines(rb: ReportBuilder, lines: pd.DataFrame, company: str) -> pd.DataFrame:
    """Row-level checks on one file's annualised lines (PRD 3.3).

    Adds ``price_comparable`` and ``price_exclusion`` and reports amount
    mismatches, non-positive prices, returns, duplicates and missing units.
    """
    f = lines
    qty, price, amount = f["quantity"], f["unit_price"], f["line_amount"]
    tolerance = np.maximum(MISMATCH_FLOOR, MISMATCH_SHARE * amount.abs())
    mismatch = (amount - qty * price).abs() > tolerance
    nonpositive = (price <= 0) & (qty > 0)
    negative = qty < 0
    key_columns = list(COLUMNS)
    duplicate = f[key_columns].duplicated(keep="first")
    has_item = f["item_code"].notna() | f["mpn"].notna()
    no_uom = has_item & f["uom"].isna()

    reason = np.select([mismatch, nonpositive], ["amount_mismatch", "non_positive_price"], None)
    f["price_exclusion"] = pd.Series(reason, index=f.index, dtype=object)
    f["price_comparable"] = f["price_exclusion"].isna()

    def value(mask: pd.Series) -> float:
        return float(f.loc[mask, "amount"].abs().sum())

    cases = (
        (
            "amount_mismatch",
            "warning",
            mismatch,
            "line_amount differs from quantity x unit_price by more than 1%. line_amount is "
            "trusted for spend; the rows are excluded from price comparison.",
            "Check the line amounts and unit prices.",
        ),
        (
            "non_positive_price",
            "warning",
            nonpositive,
            "unit_price is zero or negative with a positive quantity. The rows are excluded "
            "from price comparison.",
            "Check the unit prices.",
        ),
        (
            "negative_quantity",
            "info",
            negative,
            "Returns and credits. They are netted by summing quantity and amount within the "
            "same buying group and item.",
            "No action needed.",
        ),
        (
            "duplicate_rows",
            "warning",
            duplicate,
            "Rows identical on every field to an earlier row. They are kept; the count and "
            "value are shown for review.",
            "Remove duplicates from the extract if they are not genuine repeat purchases.",
        ),
        (
            "uom_missing",
            "warning",
            no_uom,
            "Rows with an item code or MPN but no unit of measure. They cannot be converted "
            "and are excluded from price comparison.",
            "Fill in uom.",
        ),
    )
    for rule, severity, mask, message, fix in cases:
        if mask.any():
            rb.add(
                company,
                rule,
                severity,
                f"{plural(int(mask.sum()), 'row')}: {message}",
                fix,
                affected=_rows_of(f, mask),
                amount=value(mask),
            )
    return f


def window_months(period_end: pd.Period) -> tuple[int, int]:
    """First and last month number of the 12-month window ending at ``period_end``."""
    last = period_end.year * 12 + period_end.month - 1
    return last - 11, last


_PERIOD_RE = re.compile(r"^\d{4}-\d{2}")


def to_period(value: object) -> pd.Period:
    """Coerce a month-like value (``"2024-06"``, a date, a ``Period``) to a monthly period."""
    if isinstance(value, pd.Period):
        return value.asfreq("M")
    if isinstance(value, str) and not _PERIOD_RE.match(value.strip()):
        raise ValueError("period_end must be a month such as 2024-06")
    return pd.Period(value, freq="M")  # type: ignore[call-overload]
