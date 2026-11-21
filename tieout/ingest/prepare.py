"""Turn two raw files into the ``lines`` frame (ARCHITECTURE.md)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tieout.ingest.schema import COLUMNS
from tieout.ingest.validate import (
    BlockingValidationError,
    ParsedFile,
    ReportBuilder,
    add_parse_findings,
    affected_rows,
    affected_value,
    build_lines,
    check_lines,
    month_numbers,
    normalise_fx,
    parse_file,
    plural,
    to_period,
    window_months,
)
from tieout.normalise.items import normalise_manufacturer
from tieout.normalise.taxonomy import apply_category_map, none_for_missing, unmapped_spend
from tieout.normalise.units import convert_units

__all__ = ["Prepared", "make_item_keys", "prepare"]

_ADDED_AT_VALIDATION = (
    "amount",
    "unit_price_rc",
    "quantity_ann",
    "price_comparable",
    "price_exclusion",
)
_ADDED_AT_NORMALISATION = (
    "l1_code",
    "l2_code",
    "family",
    "uom_dimension",
    "category_type",
    "base_unit",
    "base_factor",
    "conv_status",
    "qty_base",
    "price_base",
    "vendor_key",
    "item_key",
)
LINES_COLUMNS = (
    *COLUMNS,
    "company",
    "source_file",
    "source_row",
    "line_id",
    *_ADDED_AT_VALIDATION,
    *_ADDED_AT_NORMALISATION,
)
COMPANY_FILES = ("acquirer", "target")


@dataclass(frozen=True)
class Prepared:
    """Output of :func:`prepare`."""

    lines: pd.DataFrame
    data_quality: pd.DataFrame
    meta: dict[str, Any]
    affected_rows: pd.DataFrame

    def rows_for(self, rule: str, company: str | None = None) -> pd.DataFrame:
        """Rows behind a data-quality finding (company, rule, source_row, line_id)."""
        return affected_rows(self.affected_rows, rule, company)


def make_item_keys(lines: pd.DataFrame) -> pd.Series:
    """``item_code``, else ``MPN:{mpn_norm}|{manufacturer_norm}``, else ``None``.

    ``mpn_norm`` is the MPN upper-cased with only letters and digits kept;
    ``manufacturer_norm`` is the V0-normalised manufacturer (PRD 4.3).
    """
    code = lines["item_code"].astype("string").str.strip()
    mpn = lines["mpn"].astype("string").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    mpn = mpn.where(mpn != "", pd.NA)
    makers = lines["manufacturer"].astype(object)
    names = {m: normalise_manufacturer(m) for m in makers.dropna().unique()}
    maker = pd.Series([names.get(m, "") for m in makers], index=lines.index, dtype="string")
    fallback = "MPN:" + mpn + "|" + maker
    key = code.where(code.notna() & (code != ""), fallback)
    return none_for_missing(key)


def _fail(rb: ReportBuilder, parsed: Mapping[str, ParsedFile], extra: str | None = None) -> None:
    for p in parsed.values():
        add_parse_findings(rb, p, 1.0)
    if extra is not None:
        rb.add(
            extra,
            "no_lines_in_window",
            "blocking",
            "No usable lines fall inside the 12-month window.",
            "Check the dates or set period_end to a month the file covers.",
        )
    raise BlockingValidationError(rb.build())


def _resolve_window(
    parsed: Mapping[str, ParsedFile], period_end: object, rb: ReportBuilder
) -> tuple[pd.Period, dict[str, pd.Series], dict[str, int]]:
    months = {c: month_numbers(p.frame["doc_date"]).where(~p.excluded) for c, p in parsed.items()}
    if period_end is None:
        for company, series in months.items():
            if series.notna().sum() == 0:
                _fail(rb, parsed, company)
        latest = min(int(s.max()) for s in months.values())
        end = pd.Period(year=latest // 12, month=latest % 12 + 1, freq="M")
    else:
        end = to_period(period_end)
    first, last = window_months(end)
    inside = {c: (s >= first) & (s <= last) for c, s in months.items()}
    counts = {c: int(months[c][inside[c]].nunique()) for c in parsed}
    for company, count in counts.items():
        if count == 0:
            _fail(rb, parsed, company)
    return end, inside, counts


def prepare(
    acq: pd.DataFrame,
    tgt: pd.DataFrame,
    *,
    fx: Mapping[str, float] | pd.DataFrame,
    taxonomy: pd.DataFrame,
    category_map: pd.DataFrame | None = None,
    period_end: str | dt.date | pd.Period | None = None,
    aggregated: bool = False,
    reporting_currency: str = "USD",
) -> Prepared:
    """Validate, annualise, convert and map two raw files into ``lines``.

    ``acq`` and ``tgt`` are frames from :func:`tieout.ingest.load.load_file`.
    Raises :class:`BlockingValidationError` (carrying the report) when a
    blocking rule fires. See PRD 3.3 for the rules and ARCHITECTURE.md for the
    output columns.
    """
    rates = normalise_fx(fx, reporting_currency)
    parsed = {
        "acquirer": parse_file(acq, "acquirer", fx=rates, aggregated=aggregated),
        "target": parse_file(tgt, "target", fx=rates, aggregated=aggregated),
    }
    rb = ReportBuilder()
    if any(p.is_blocked for p in parsed.values()):
        _fail(rb, parsed)

    window: dict[str, pd.Series]
    if aggregated:
        end = None
        window = {c: ~p.excluded for c, p in parsed.items()}
        months = {c: 12 for c in parsed}
        scale = {c: 1.0 for c in parsed}
    else:
        end, inside, months = _resolve_window(parsed, period_end, rb)
        window = {c: inside[c] & ~parsed[c].excluded for c in parsed}
        scale = {c: 12 / months[c] for c in parsed}

    frames = []
    for company, p in parsed.items():
        add_parse_findings(rb, p, scale[company])
        outside = ~p.excluded & ~window[company]
        if outside.any():
            f = p.frame
            rb.add(
                company,
                "outside_window",
                "info",
                f"{int(outside.sum()):,} rows fall outside the 12-month window and are ignored.",
                "Set period_end if a different window is wanted.",
                affected=f.loc[outside, ["company", "source_row", "line_id"]],
                amount=affected_value(f, outside, 1.0),
            )
        lines = check_lines(rb, build_lines(p, window[company], scale[company]), company)
        if scale[company] > 1 and not aggregated:
            rb.add(
                company,
                "partial_year_scaled",
                "warning",
                f"Only {months[company]} of 12 window months have data; quantities and spend are "
                f"scaled by {scale[company]:.2f} (12 / {months[company]}) on every output.",
                "Supply twelve months of data for an unscaled analysis.",
                rows=len(lines),
                amount=float(lines["amount"].sum()),
            )
        frames.append(lines)

    lines = pd.concat(frames, ignore_index=True)
    lines = lines.sort_values(["company", "source_row"], kind="stable").reset_index(drop=True)
    lines["vendor_key"] = lines["company"] + ":" + lines["vendor_id"].astype(str)
    lines["item_key"] = make_item_keys(lines)
    lines = apply_category_map(lines, category_map, taxonomy)
    lines = convert_units(lines)
    lines = _price_exclusions(lines)
    _add_normalisation_findings(rb, lines, category_map, taxonomy)
    features = _add_feature_findings(rb, parsed, aggregated)

    lines = lines[list(LINES_COLUMNS)]
    report = rb.build()
    meta = _meta(lines, end, months, scale, rates, reporting_currency, aggregated, features, parsed)
    return Prepared(lines, report.frame, meta, report.affected)


def _price_exclusions(lines: pd.DataFrame) -> pd.DataFrame:
    """Extend the price-comparison exclusion with lines that cannot be compared (PRD 3.5, 4.6)."""
    extra = np.select(
        [lines["item_key"].isna(), lines["conv_status"] == "unconverted"],
        ["no_item", "unit_unconverted"],
        None,
    )
    reason = lines["price_exclusion"].where(
        lines["price_exclusion"].notna(), pd.Series(extra, index=lines.index, dtype=object)
    )
    lines["price_exclusion"] = none_for_missing(reason)
    lines["price_comparable"] = lines["price_exclusion"].isna()
    return lines


def _rows(lines: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    return lines.loc[mask, ["company", "source_row", "line_id"]]


def _add_normalisation_findings(
    rb: ReportBuilder,
    lines: pd.DataFrame,
    category_map: pd.DataFrame | None,
    taxonomy: pd.DataFrame,
) -> None:
    for company in COMPANY_FILES:
        mine = lines["company"] == company
        unmapped = mine & lines["l2_code"].isna()
        if unmapped.any():
            rb.add(
                company,
                "unmapped_category",
                "warning",
                f"{int(unmapped.sum()):,} lines are in categories that are not mapped to the "
                "common taxonomy. They count as spend but cannot be matched or used in any lever.",
                "Map the categories on the Map categories step.",
                affected=_rows(lines, unmapped),
                amount=float(lines.loc[unmapped, "amount"].abs().sum()),
            )
        unconverted = mine & (lines["conv_status"] == "unconverted")
        if unconverted.any():
            rb.add(
                company,
                "unit_unconverted",
                "info",
                f"{int(unconverted.sum()):,} item lines have a unit that cannot be converted "
                "(unknown unit or a pack unit with no pack size). They count as spend and are "
                "excluded from price comparison.",
                "Add pack_qty or a pack size to the description, or correct the unit.",
                affected=_rows(lines, unconverted),
                amount=float(lines.loc[unconverted, "amount"].abs().sum()),
            )
        no_item = mine & lines["item_key"].isna()
        if no_item.any():
            rb.add(
                company,
                "not_item_addressable",
                "info",
                f"{plural(int(no_item.sum()), 'line')} have no item code and no MPN. They take "
                "part in "
                "vendor matching, consolidation and payment terms, never in price harmonisation.",
                "No action needed.",
                affected=_rows(lines, no_item),
                amount=float(lines.loc[no_item, "amount"].abs().sum()),
            )
    if category_map is not None and not category_map.empty:
        unknown = ~category_map["l2_code"].isin(taxonomy["l2_code"])
        if unknown.any():
            codes = ", ".join(sorted(set(category_map.loc[unknown, "l2_code"].astype(str)))[:10])
            rb.add(
                "both",
                "unknown_l2_code",
                "warning",
                f"{int(unknown.sum()):,} category mappings use an l2_code that is not in the "
                f"taxonomy ({codes}); those categories are treated as unmapped.",
                "Correct the l2_code values in the category map.",
                rows=int(unknown.sum()),
            )


def _add_feature_findings(
    rb: ReportBuilder, parsed: Mapping[str, ParsedFile], aggregated: bool
) -> dict[str, bool]:
    usable = {c: p.frame.loc[~p.excluded] for c, p in parsed.items()}
    has_contract = {c: bool(f["contract_end_date"].notna().any()) for c, f in usable.items()}
    has_dates = {c: bool(f["payment_date"].notna().any()) for c, f in usable.items()}
    has_terms = {
        c: bool(f["payment_terms_days"].notna().any() or has_dates[c]) for c, f in usable.items()
    }
    if not any(has_contract.values()):
        rb.add(
            "both",
            "no_contract_end_date",
            "info",
            "No contract_end_date in either file; phasing falls back to the global ramp.",
            "Supply contract_end_date for contract-aware phasing.",
        )
    if not any(has_dates.values()) and not aggregated:
        rb.add(
            "both",
            "no_payment_date",
            "info",
            "No payment_date in either file; the payment-terms lever uses stated terms.",
            "Supply payment_date to use observed days-to-pay.",
        )
    for company, present in has_terms.items():
        if not present:
            rb.add(
                company,
                "no_payment_terms",
                "warning",
                "Neither payment_terms_days nor payment_date is present; the payment-terms "
                "lever (lever 3) is switched off.",
                "Supply payment_terms_days or payment_date.",
            )
    if aggregated:
        rb.add(
            "both",
            "aggregated_mode",
            "info",
            "Aggregated mode: no 12-month window or scaling is applied, the three-line benchmark "
            "test is skipped and observed days-to-pay is unavailable.",
            "Upload line-level data to enable these.",
        )
    return {
        "contract_phasing": any(has_contract.values()),
        "payment_terms": all(has_terms.values()),
        "observed_days_to_pay": any(has_dates.values()) and not aggregated,
        "benchmark_line_test": not aggregated,
    }


def _by_company(lines: pd.DataFrame, mask: pd.Series | None = None) -> dict[str, float]:
    frame = lines if mask is None else lines[mask]
    sums = frame.groupby("company")["amount"].sum()
    out = {c: float(sums.get(c, 0.0)) for c in COMPANY_FILES}
    out["total"] = float(sum(out.values()))
    return out


def _meta(
    lines: pd.DataFrame,
    end: pd.Period | None,
    months: Mapping[str, int],
    scale: Mapping[str, float],
    rates: Mapping[str, float],
    reporting_currency: str,
    aggregated: bool,
    features: Mapping[str, bool],
    parsed: Mapping[str, ParsedFile],
) -> dict[str, Any]:
    in_scope = _by_company(lines)
    mapped = lines[lines["l2_code"].notna()]
    per_l2 = mapped.groupby(["l2_code", "company"])["amount"].sum().unstack("company").fillna(0.0)
    both = per_l2.reindex(columns=list(COMPANY_FILES), fill_value=0.0)
    addressable_l2 = sorted(both.index[(both > 0).all(axis=1)])
    addressable = _by_company(lines, lines["l2_code"].isin(addressable_l2))
    no_item = _by_company(lines, lines["item_key"].isna())
    unmapped = _by_company(lines, lines["l2_code"].isna())

    def share(part: Mapping[str, float]) -> dict[str, float]:
        return {k: (part[k] / in_scope[k] if in_scope[k] else 0.0) for k in part}

    period = None
    if end is not None:
        period = {
            "start": str(end - 11),
            "end": str(end),
            "months": 12,
        }
    return {
        "aggregated": aggregated,
        "period": period,
        "months_with_data": None if aggregated else dict(months),
        "scaling_factor": {c: float(scale[c]) for c in COMPANY_FILES},
        "scaled": any(scale[c] > 1 for c in COMPANY_FILES),
        "reporting_currency": reporting_currency.upper(),
        "fx_rates": dict(sorted(rates.items())),
        "rows": {c: int((lines["company"] == c).sum()) for c in COMPANY_FILES},
        "rows_in_file": {c: parsed[c].n_rows for c in COMPANY_FILES},
        "in_scope_spend": in_scope,
        "addressable_spend": addressable,
        "addressable_l2": addressable_l2,
        "unmapped_spend": unmapped,
        "unmapped_by_category": unmapped_spend(lines).to_dict("records"),
        "not_item_addressable": {
            "amount": no_item,
            "share": share(no_item),
            "rows": {
                c: int((lines["company"].eq(c) & lines["item_key"].isna()).sum())
                for c in COMPANY_FILES
            },
        },
        "features": dict(features),
    }
