import numpy as np
import pandas as pd
import pytest
from ingest_fixtures import FX, many

from tieout.ingest import BlockingValidationError
from tieout.ingest.validate import (
    exceeds_blocking_share,
    normalise_fx,
    parse_dates,
    parse_numbers,
)


def rule(prepared, name, company=None):
    dq = prepared.data_quality
    hit = dq[dq["rule"] == name]
    if company is not None:
        hit = hit[hit["company"] == company]
    return hit


def blocked(run, acq, tgt=None, **kwargs):
    with pytest.raises(BlockingValidationError) as info:
        run(acq, tgt, **kwargs)
    return info.value.report


def year(**overrides):
    """Twelve rows, one in each month from 2023-04 to 2024-03."""
    months = [f"2023-{m:02d}-10" for m in range(4, 13)] + [f"2024-{m:02d}-10" for m in (1, 2, 3)]
    return [{"doc_date": d, "po_line": str(i), **overrides} for i, d in enumerate(months)]


# ---- type parsing ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1234.5", 1234.5),
        ("1,234.50", 1234.5),
        ("$ 1,234", 1234.0),
        ("(12.5)", -12.5),
        ("12.5-", -12.5),
        ("-3", -3.0),
        ("1e3", 1000.0),
        ("abc", np.nan),
        ("inf", np.nan),
        ("nan", np.nan),
        ("", np.nan),
        (None, np.nan),
    ],
)
def test_parse_numbers(text, expected):
    value = parse_numbers(pd.Series([text], dtype=object)).iloc[0]
    assert (np.isnan(value) and np.isnan(expected)) or value == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-03-31", "2024-03-31"),
        ("2024/3/1", "2024-03-01"),
        ("2024-03-31 00:00:00", "2024-03-31"),
        ("2024-03-31T08:15:00", "2024-03-31"),
        ("20240331", "2024-03-31"),
        ("03/31/2024", "2024-03-31"),
        ("31/03/2024", "2024-03-31"),
        ("31-Mar-2024", "2024-03-31"),
        ("5 January 2024", "2024-01-05"),
        ("2024-13-01", None),
        ("2024-02-30", None),
        ("1850-01-01", None),
        ("not a date", None),
        ("", None),
    ],
)
def test_parse_dates(text, expected):
    value = parse_dates(pd.Series([text], dtype=object)).iloc[0]
    assert (pd.isna(value) and expected is None) or str(value.date()) == expected


def test_one_percent_rule_is_strictly_greater():
    assert not exceeds_blocking_share(1, 100)
    assert exceeds_blocking_share(2, 100)
    assert not exceeds_blocking_share(0, 0)
    assert exceeds_blocking_share(1, 99)


def test_country_and_other_text_are_normalised(run):
    p = run(
        [
            {"vendor_country": "us", "uom": " ea ", "spend_type": "Direct", "currency": "usd"},
            {"vendor_country": "USA", "spend_type": "other", "po_line": "2"},
        ]
    )
    acq = p.lines[p.lines["company"] == "acquirer"]
    assert acq["vendor_country"].tolist() == ["US", None]
    assert acq["uom"].tolist() == ["EA", "EA"]
    assert acq["spend_type"].tolist() == ["direct", None]
    assert acq["currency"].tolist() == ["USD", "USD"]


# ---- required columns -----------------------------------------------------


def test_missing_required_column_blocks(run, raw):
    acq = raw(year()).drop(columns=["currency"])
    from tieout.ingest import prepare
    from tieout.reference import load_taxonomy

    with pytest.raises(BlockingValidationError) as info:
        prepare(acq, raw(year(), "target"), fx=FX, taxonomy=load_taxonomy())
    frame = info.value.report.frame
    row = frame[frame["rule"] == "required_column_missing"].iloc[0]
    assert (row["company"], row["severity"]) == ("acquirer", "blocking")
    assert "currency" in row["message"]
    assert "currency" in str(info.value)


def test_uom_is_required_when_rows_have_items(raw):
    from tieout.ingest import prepare
    from tieout.reference import load_taxonomy

    acq = raw(year()).drop(columns=["uom"])
    with pytest.raises(BlockingValidationError) as info:
        prepare(acq, raw(year(), "target"), fx=FX, taxonomy=load_taxonomy())
    message = info.value.report.frame.query("rule == 'required_column_missing'").iloc[0]["message"]
    assert "uom" in message


def test_uom_not_required_when_no_item_codes_or_mpns(run):
    rows = [{"item_code": None, "uom": None, **r} for r in year()]
    assert len(run(rows).lines) == 24


def test_empty_file_blocks(run, raw):
    from tieout.ingest import prepare
    from tieout.reference import load_taxonomy

    empty = raw(year()).iloc[0:0]
    with pytest.raises(BlockingValidationError) as info:
        prepare(empty, raw(year(), "target"), fx=FX, taxonomy=load_taxonomy())
    assert "no_rows" in set(info.value.report.frame["rule"])


def test_doc_date_not_required_in_aggregated_mode(run):
    rows = [{"doc_date": None}]
    assert len(run(rows, aggregated=True).lines) == 2


# ---- the 1% rule ----------------------------------------------------------

BAD_VALUES = [
    ("unparseable_date", {"doc_date": "not a date"}),
    ("unparseable_number", {"quantity": "abc"}),
    ("unparseable_number", {"unit_price": ""}),
    ("unparseable_number", {"line_amount": "n/a"}),
    ("unparseable_currency", {"currency": "US"}),
    ("unparseable_currency", {"currency": None}),
]


@pytest.mark.parametrize(("name", "bad"), BAD_VALUES)
def test_exactly_one_percent_unparseable_is_a_warning(run, name, bad):
    rows = many(99) + [bad]
    p = run(rows)
    hit = rule(p, name, "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("warning", 1)
    assert len(p.lines[p.lines["company"] == "acquirer"]) == 99  # excluded
    assert p.rows_for(name, "acquirer")["source_row"].tolist() == [101]


@pytest.mark.parametrize(("name", "bad"), BAD_VALUES)
def test_just_over_one_percent_blocks(run, name, bad):
    report = blocked(run, many(98) + [bad, {**bad, "po_line": "x"}])
    hit = report.frame[report.frame["rule"] == name].iloc[0]
    assert (hit["severity"], hit["company"]) == ("blocking", "acquirer")
    assert report.blocking
    assert len(report.rows_for(name, "acquirer")) == 2


def test_one_percent_counts_rows_across_date_number_and_currency(run):
    rows = many(98) + [{"doc_date": "bad"}, {"quantity": "bad", "po_line": "x"}]
    report = blocked(run, rows)
    assert set(report.frame.loc[report.frame["severity"] == "blocking", "rule"]) == {
        "unparseable_date",
        "unparseable_number",
    }


def test_a_row_with_two_problems_counts_once(run):
    p = run(many(99) + [{"doc_date": "bad", "quantity": "bad"}])
    assert rule(p, "unparseable_date")["severity"].iloc[0] == "warning"


def test_blocking_is_per_file(run):
    bad = many(98) + [{"currency": "x"}, {"currency": "y", "po_line": "z"}]
    report = blocked(run, many(100), bad)
    blocking = report.frame[report.frame["severity"] == "blocking"]
    assert set(blocking["company"]) == {"target"}


def test_unparseable_value_amount_is_reported(run):
    rows = many(99) + [{"quantity": "bad", "line_amount": "400"}]
    p = run(rows, period_end="2024-03")
    assert rule(p, "unparseable_number")["amount"].iloc[0] == pytest.approx(400 * 12)


def test_blank_vendor_id_follows_the_one_percent_rule(run):
    p = run(many(99) + [{"vendor_id": None}])
    assert rule(p, "vendor_id_blank")["severity"].iloc[0] == "warning"
    report = blocked(run, many(98) + [{"vendor_id": None}, {"vendor_id": None, "po_line": "x"}])
    assert "vendor_id_blank" in set(
        report.frame.loc[report.frame["severity"] == "blocking", "rule"]
    )


def test_unusable_optional_values_are_blanked_with_a_warning(run):
    rows = [{"pack_qty": "x"}, {"payment_terms_days": "-5"}, {"payment_date": "never"}]
    p = run([{**r, "po_line": str(i)} for i, r in enumerate(rows)])
    hit = rule(p, "unparseable_optional", "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("warning", 3)
    assert len(p.lines) == 6  # rows are kept
    assert p.lines["payment_terms_days"].isna().all()


# ---- FX -------------------------------------------------------------------


def test_fx_conversion_to_reporting_currency(run):
    rows = [{"currency": "CAD", "quantity": "10", "unit_price": "10", "line_amount": "100"}]
    p = run(rows)
    line = p.lines.iloc[0]
    assert line["amount"] == pytest.approx(100 * 0.73 * 12)
    assert line["unit_price_rc"] == pytest.approx(7.3)
    assert line["line_amount"] == 100  # native amount kept as received


def test_lower_case_currency_is_accepted(run):
    assert run([{"currency": "eur", "line_amount": "50"}]).lines["amount"].iloc[0] == pytest.approx(
        50 * 1.08 * 12
    )


def test_exactly_one_percent_missing_from_fx_is_a_warning(run):
    p = run(many(99) + [{"currency": "JPY"}])
    hit = rule(p, "currency_not_in_fx", "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("warning", 1)
    assert "JPY" in hit["message"]
    assert len(p.lines[p.lines["company"] == "acquirer"]) == 99


def test_just_over_one_percent_missing_from_fx_blocks(run):
    report = blocked(run, many(98) + [{"currency": "JPY"}, {"currency": "JPY", "po_line": "x"}])
    hit = report.frame[report.frame["rule"] == "currency_not_in_fx"].iloc[0]
    assert hit["severity"] == "blocking"


def test_reporting_currency_label_and_table_rules():
    assert normalise_fx({"usd": 1.0, "cad": 0.73}, "USD") == {"USD": 1.0, "CAD": 0.73}
    assert normalise_fx({"CAD": 0.73}, "usd")["USD"] == 1.0
    with pytest.raises(ValueError, match="reporting currency"):
        normalise_fx({"EUR": 1.08}, "EUR")
    with pytest.raises(ValueError, match="positive"):
        normalise_fx({"EUR": 0.0}, "USD")
    frame = pd.DataFrame({"currency": ["EUR"], "rate": [1.0]})
    assert normalise_fx(frame, "EUR") == {"EUR": 1.0}


def test_other_reporting_currency(run):
    fx = {"EUR": 1.0, "USD": 0.9, "CAD": 0.7}
    p = run(
        [{"line_amount": "100", "quantity": "10", "unit_price": "10"}],
        fx=fx,
        reporting_currency="eur",
    )
    assert p.lines["amount"].iloc[0] == pytest.approx(100 * 0.9 * 12)
    assert p.meta["reporting_currency"] == "EUR"


# ---- row-level warnings ---------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "quantity", "price", "flagged"),
    [
        ("100", "1", "99", False),  # difference is exactly 1%
        ("100", "1", "98.9", True),  # just over
        ("100", "1", "100", False),
        ("0.5", "1", "0.505", False),  # below the 0.01 floor
        ("0.5", "1", "0.52", True),  # above the floor
        ("-100", "-1", "99", False),
        ("-100", "-1", "98.9", True),
    ],
)
def test_amount_mismatch_boundary(run, amount, quantity, price, flagged):
    rows = [{"line_amount": amount, "quantity": quantity, "unit_price": price}]
    p = run(rows, period_end="2024-03")
    line = p.lines.iloc[0]
    hit = rule(p, "amount_mismatch", "acquirer")
    assert hit.empty == (not flagged)
    assert line["price_comparable"] == (not flagged)
    assert line["price_exclusion"] == ("amount_mismatch" if flagged else None)
    assert line["amount"] == pytest.approx(float(amount) * 12)  # line_amount is trusted
    if flagged:
        assert hit["severity"].iloc[0] == "warning"
        assert hit["amount"].iloc[0] == pytest.approx(abs(float(amount)) * 12)


def test_non_positive_price_with_positive_quantity(run):
    rows = [
        {"unit_price": "0", "line_amount": "0", "po_line": "1"},
        {"unit_price": "-2", "line_amount": "-20", "po_line": "2"},
        {"unit_price": "-2", "quantity": "-10", "line_amount": "20", "po_line": "3"},
        {"po_line": "4"},
    ]
    p = run(rows)
    acq = p.lines[p.lines["company"] == "acquirer"].set_index("po_line")
    assert acq["price_exclusion"].to_dict() == {
        "1": "non_positive_price",
        "2": "non_positive_price",
        "3": None,
        "4": None,
    }
    hit = rule(p, "non_positive_price", "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("warning", 2)


def test_negative_quantity_is_info(run):
    rows = [
        {"po_line": "1"},
        {"quantity": "-4", "line_amount": "-20", "po_line": "2"},
    ]
    p = run(rows, period_end="2024-03")
    hit = rule(p, "negative_quantity", "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("info", 1)
    assert hit["amount"] == pytest.approx(20 * 12)
    assert len(p.lines[p.lines["company"] == "acquirer"]) == 2  # kept for netting later


def test_duplicate_rows_are_kept_and_reported(run):
    p = run([{}, {}, {"po_line": "2"}], period_end="2024-03")
    hit = rule(p, "duplicate_rows", "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("warning", 1)
    assert hit["amount"] == pytest.approx(50 * 12)
    assert len(p.lines[p.lines["company"] == "acquirer"]) == 3


def test_no_duplicates_no_finding(run):
    assert rule(run(many(3)), "duplicate_rows").empty


def test_missing_uom_on_item_rows(run):
    p = run([{"uom": None, "po_line": "1"}, {"item_code": None, "po_line": "2"}])
    hit = rule(p, "uom_missing", "acquirer").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("warning", 1)
    acq = p.lines[p.lines["company"] == "acquirer"].set_index("po_line")
    assert acq.loc["1", "price_exclusion"] == "unit_unconverted"


# ---- features and info ----------------------------------------------------


def test_missing_contract_and_payment_dates_are_info(run):
    p = run(year())
    for name in ("no_contract_end_date", "no_payment_date"):
        hit = rule(p, name).iloc[0]
        assert (hit["severity"], hit["company"]) == ("info", "both")
    assert p.meta["features"]["contract_phasing"] is False
    assert p.meta["features"]["observed_days_to_pay"] is False


def test_contract_and_payment_dates_enable_features(run):
    p = run(
        year(contract_end_date="2025-01-31", payment_date="2024-04-30", payment_terms_days="30")
    )
    assert rule(p, "no_contract_end_date").empty
    assert rule(p, "no_payment_date").empty
    assert p.meta["features"] == {
        "contract_phasing": True,
        "payment_terms": True,
        "observed_days_to_pay": True,
        "benchmark_line_test": True,
    }


def test_payment_terms_lever_is_off_without_terms_or_dates_in_a_file(run):
    with_terms = year(payment_terms_days="45")
    p = run(with_terms, year())
    hit = rule(p, "no_payment_terms").iloc[0]
    assert (hit["severity"], hit["company"]) == ("warning", "target")
    assert p.meta["features"]["payment_terms"] is False
    assert rule(run(with_terms), "no_payment_terms").empty


# ---- annualisation --------------------------------------------------------


def test_full_year_is_not_scaled(run):
    p = run(year())
    assert p.meta["scaling_factor"] == {"acquirer": 1.0, "target": 1.0}
    assert p.meta["scaled"] is False
    assert rule(p, "partial_year_scaled").empty
    assert p.meta["period"] == {"start": "2023-04", "end": "2024-03", "months": 12}
    assert p.lines["amount"].sum() == pytest.approx(2 * 12 * 50)


def test_partial_year_is_scaled_and_flagged(run):
    acq = [
        {"doc_date": "2023-10-05", "po_line": "1"},
        {"doc_date": "2023-10-20", "po_line": "2"},
        {"doc_date": "2024-01-05", "po_line": "3"},
        {"doc_date": "2024-03-05", "po_line": "4"},
    ]
    p = run(acq, year())
    # acquirer has 3 months with data -> factor 4; target has all 12
    assert p.meta["scaling_factor"] == {"acquirer": 4.0, "target": 1.0}
    assert p.meta["months_with_data"] == {"acquirer": 3, "target": 12}
    assert p.meta["scaled"] is True
    a = p.lines[p.lines["company"] == "acquirer"]
    assert a["amount"].tolist() == [200.0] * 4
    assert a["quantity_ann"].tolist() == [40.0] * 4
    assert a["unit_price_rc"].tolist() == [5.0] * 4  # prices are not scaled
    hit = rule(p, "partial_year_scaled").iloc[0]
    assert (hit["company"], hit["severity"]) == ("acquirer", "warning")
    assert "3 of 12" in hit["message"]
    assert hit["amount"] == pytest.approx(800)


def test_gap_months_count_only_months_with_lines(run):
    acq = [{"doc_date": "2023-04-05"}, {"doc_date": "2024-03-05", "po_line": "2"}]
    p = run(acq, year())
    assert p.meta["scaling_factor"]["acquirer"] == 6.0


def test_default_period_end_is_the_earlier_latest_month(run):
    acq = year()  # latest 2024-03
    tgt = [{"doc_date": f"2023-{m:02d}-10", "po_line": str(m)} for m in range(7, 13)] + [
        {"doc_date": "2024-06-10", "po_line": "99"}
    ]
    p = run(acq, tgt)
    assert p.meta["period"]["end"] == "2024-03"
    out = rule(p, "outside_window", "target").iloc[0]
    assert (out["severity"], out["rows"]) == ("info", 1)
    assert len(p.lines[p.lines["company"] == "target"]) == 6
    assert rule(p, "outside_window", "acquirer").empty


def test_explicit_period_end_sets_the_window(run):
    rows = year()
    p = run(rows, period_end="2024-01")
    assert p.meta["period"] == {"start": "2023-02", "end": "2024-01", "months": 12}
    a = p.lines[p.lines["company"] == "acquirer"]
    assert len(a) == 10  # 2023-04 .. 2024-01
    assert p.meta["scaling_factor"]["acquirer"] == pytest.approx(1.2)
    assert rule(p, "outside_window", "acquirer")["rows"].iloc[0] == 2
    assert run(rows, period_end=pd.Period("2024-01")).meta["period"]["end"] == "2024-01"
    assert run(rows, period_end=pd.Timestamp("2024-01-17")).meta["period"]["end"] == "2024-01"


def test_bad_period_end(run):
    with pytest.raises(ValueError, match="month"):
        run(year(), period_end="soon")


def test_no_lines_in_window_blocks(run):
    report = blocked(run, year(), period_end="2026-01")
    assert "no_lines_in_window" in set(report.frame["rule"])
    assert report.blocking


# ---- aggregated mode ------------------------------------------------------


def test_aggregated_mode_skips_window_and_scaling(run):
    rows = [{"doc_date": None, "quantity": "1000", "unit_price": "2", "line_amount": "2000"}]
    p = run(rows, aggregated=True)
    assert p.meta["aggregated"] is True
    assert p.meta["period"] is None
    assert p.meta["scaling_factor"] == {"acquirer": 1.0, "target": 1.0}
    assert p.lines["amount"].tolist() == [2000.0, 2000.0]
    assert p.lines["quantity_ann"].tolist() == [1000.0, 1000.0]
    features = p.meta["features"]
    assert features["benchmark_line_test"] is False
    assert features["observed_days_to_pay"] is False
    hit = rule(p, "aggregated_mode").iloc[0]
    assert hit["severity"] == "info"
    assert "benchmark" in hit["message"]
    assert rule(p, "partial_year_scaled").empty


def test_aggregated_mode_ignores_unparseable_dates(run):
    rows = [{"doc_date": "whenever"}] * 1
    assert len(run(rows, aggregated=True).lines) == 2
    assert rule(run(rows, aggregated=True), "unparseable_date").empty


def test_aggregated_mode_keeps_all_dates_unfiltered(run):
    rows = [{"doc_date": "1999-01-01"}, {"doc_date": "2030-01-01", "po_line": "2"}]
    assert len(run(rows, aggregated=True).lines) == 4


# ---- output ---------------------------------------------------------------


def test_data_quality_frame_shape_and_order(run):
    rows = many(99) + [{"currency": "x"}]
    dq = run(rows).data_quality
    assert list(dq.columns) == ["company", "rule", "severity", "rows", "amount", "message", "fix"]
    assert set(dq["severity"]) <= {"blocking", "warning", "info"}
    order = dq["severity"].map({"blocking": 0, "warning": 1, "info": 2})
    assert order.is_monotonic_increasing
    assert dq["fix"].str.len().gt(0).all()


def test_lines_columns_follow_the_contract(run):
    lines = run(year()).lines
    for column in (
        "site",
        "doc_date",
        "company",
        "source_file",
        "source_row",
        "line_id",
        "amount",
        "unit_price_rc",
        "quantity_ann",
        "price_comparable",
        "price_exclusion",
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
    ):
        assert column in lines
    first = lines.iloc[0]
    assert first["line_id"] == "acquirer:2"
    assert first["vendor_key"] == "acquirer:V1"
    assert lines["price_comparable"].dtype == bool
    assert pd.api.types.is_datetime64_any_dtype(lines["doc_date"])


def test_lines_are_sorted_and_prepare_is_deterministic(run):
    a = run(year())
    b = run(year())
    pd.testing.assert_frame_equal(a.lines, b.lines)
    pd.testing.assert_frame_equal(a.data_quality, b.data_quality)
    keys = list(zip(a.lines["company"], a.lines["source_row"], strict=True))
    assert keys == sorted(keys)


def test_report_lists_affected_rows(run):
    p = run(many(99) + [{"currency": "JPY"}], many(100))
    rows = p.rows_for("currency_not_in_fx", "acquirer")
    assert rows.columns.tolist() == ["company", "rule", "source_row", "line_id"]
    assert rows["line_id"].tolist() == ["acquirer:101"]
    assert p.rows_for("currency_not_in_fx", "target").empty


def test_blocking_error_carries_the_report(run):
    report = blocked(run, many(98) + [{"quantity": "x"}, {"quantity": "y", "po_line": "z"}])
    assert report.frame["severity"].eq("blocking").any()
    assert report.rows_for("unparseable_number", "acquirer")["source_row"].tolist() == [100, 101]
