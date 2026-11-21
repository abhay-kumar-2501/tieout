import io
import logging

import openpyxl
import pandas as pd
import pytest

from tieout.ingest import FileLimitError, UnreadableFileError, load_file
from tieout.ingest import load as load_module
from tieout.ingest.schema import MAX_BYTES, MAX_ROWS

CSV = (
    "Site,Doc Date,vendor_id,Vendor Name,junk\n"
    "P1,2024-01-02,V1,Acme,x\n"
    ",,,,\n"
    "P2,2024-01-03,V2,  Beta  ,y\n"
)


def test_limits_are_the_prd_limits():
    assert MAX_ROWS == 250_000
    assert MAX_BYTES == 50 * 1024 * 1024


def test_csv_is_read_as_text_with_load_columns():
    frame = load_file(io.StringIO(CSV), "acquirer")
    assert list(frame["site"]) == ["P1", "P2"]
    assert "junk" not in frame
    assert list(frame["vendor_name"]) == ["Acme", "Beta"]
    assert list(frame["doc_date"]) == ["2024-01-02", "2024-01-03"]  # still text
    assert list(frame["company"]) == ["acquirer"] * 2
    assert list(frame["line_id"]) == ["acquirer:2", "acquirer:4"]  # blank row 3 keeps numbering
    assert list(frame["source_row"]) == [2, 4]


def test_blank_cells_are_none():
    frame = load_file(io.StringIO("site,vendor_id\nP1,\n,V2\n"), "target")
    assert frame["vendor_id"].tolist() == [None, "V2"]
    assert frame["site"].tolist() == ["P1", None]


def test_values_stay_text():
    frame = load_file(io.StringIO("vendor_id,quantity\n00123,1e3\n"), "target")
    assert frame["vendor_id"].tolist() == ["00123"]
    assert frame["quantity"].tolist() == ["1e3"]


def test_mapping_renames_headers():
    text = "Supplier,Net Amt\nAcme,5\n"
    frame = load_file(
        io.StringIO(text), "acquirer", {"Supplier": "vendor_name", "Net Amt": "line_amount"}
    )
    assert frame.loc[0, "vendor_name"] == "Acme"
    assert frame.loc[0, "line_amount"] == "5"


def test_mapping_errors():
    with pytest.raises(ValueError, match="not in the file"):
        load_file(io.StringIO("a,b\n1,2\n"), "acquirer", {"zzz": "site"})
    with pytest.raises(ValueError, match="not schema fields"):
        load_file(io.StringIO("a,b\n1,2\n"), "acquirer", {"a": "nonsense"})
    with pytest.raises(ValueError, match="same field"):
        load_file(io.StringIO("a,b\n1,2\n"), "acquirer", {"a": "site", "b": "site"})
    with pytest.raises(ValueError, match="company"):
        load_file(io.StringIO("a\n1\n"), "buyer")


def test_semicolon_delimiter_and_bom_are_handled():
    frame = load_file(io.BytesIO("﻿site;vendor_id\nP1;V1\n".encode()), "acquirer")
    assert frame.loc[0, "site"] == "P1"
    assert frame.loc[0, "vendor_id"] == "V1"


def test_path_input_records_the_base_name(tmp_path):
    path = tmp_path / "acq_2024.csv"
    path.write_text("site\nP1\n")
    assert load_file(path, "acquirer").loc[0, "source_file"] == "acq_2024.csv"
    assert load_file(str(path), "acquirer").loc[0, "site"] == "P1"


def test_xlsx_is_read_as_text():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Site", "doc_date", "quantity", "vendor_id"])
    sheet.append(["P1", pd.Timestamp("2024-02-03").to_pydatetime(), 12.5, "V1"])
    sheet.append([None, None, None, None])
    sheet.append(["P2", "2024-02-04", 7, "V2"])
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    frame = load_file(buffer, "target")
    assert frame["quantity"].tolist() == ["12.5", "7"]
    assert frame["doc_date"].tolist()[0].startswith("2024-02-03")
    assert frame["source_row"].tolist() == [2, 4]


def test_row_limit(monkeypatch):
    monkeypatch.setattr(load_module, "MAX_ROWS", 3)
    load_file(io.StringIO("site\n1\n2\n3\n"), "acquirer")
    with pytest.raises(FileLimitError, match="rows"):
        load_file(io.StringIO("site\n1\n2\n3\n4\n"), "acquirer")


def test_xlsx_row_limit(monkeypatch):
    monkeypatch.setattr(load_module, "MAX_ROWS", 2)
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["site"])
    for i in range(3):
        sheet.append([str(i)])
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    with pytest.raises(FileLimitError, match="rows"):
        load_file(buffer, "acquirer")


def test_size_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(load_module, "MAX_BYTES", 10)
    with pytest.raises(FileLimitError, match="MB"):
        load_file(io.BytesIO(b"site\n" + b"x" * 20), "acquirer")
    path = tmp_path / "big.csv"
    path.write_bytes(b"site\n" + b"x" * 20)
    with pytest.raises(FileLimitError, match="MB"):
        load_file(path, "acquirer")


def test_unreadable_files_raise_a_clear_error():
    with pytest.raises(UnreadableFileError):
        load_file(io.BytesIO(b"PK\x03\x04 not really a workbook"), "acquirer")
    with pytest.raises(UnreadableFileError, match="xls"):
        load_file(io.BytesIO(b"\xd0\xcf\x11\xe0 old format"), "acquirer")
    with pytest.raises(UnreadableFileError):
        load_file(io.StringIO(""), "acquirer")


def test_loading_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG):
        load_file(io.StringIO(CSV), "acquirer")
    assert caplog.records == []
