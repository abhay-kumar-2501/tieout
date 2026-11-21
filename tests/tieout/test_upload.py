"""The upload flow's step logic: peek, suggest, validate, run (PRD 2.3)."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from tieout import upload
from tieout.ingest import FileLimitError, UnreadableFileError
from tieout.ingest.mapping import to_mapping


@pytest.fixture(scope="module")
def blobs(small_files) -> dict[str, bytes]:
    return {c: small_files[c].read_bytes() for c in ("acquirer", "target")}


def test_peek_reads_headers_and_rows(blobs: dict[str, bytes]) -> None:
    peek = upload.peek_file(blobs["target"], "t.csv")
    assert peek.headers[:3] == ["site", "doc_date", "vendor_id"]
    assert peek.rows == len(pd.read_csv(io.BytesIO(blobs["target"])))
    assert peek.size == len(blobs["target"])


def test_peek_refuses_over_the_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload, "MAX_ROWS", 3)
    with pytest.raises(FileLimitError, match="rows"):
        upload.peek_file(b"a,b\n1,2\n1,2\n1,2\n1,2\n")


def test_peek_refuses_over_the_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload, "MAX_BYTES", 10)
    with pytest.raises(FileLimitError, match="MB"):
        upload.peek_file(b"a,b\n" + b"1,2\n" * 10)


def test_peek_refuses_legacy_xls() -> None:
    with pytest.raises(UnreadableFileError):
        upload.peek_file(b"\xd0\xcf\x11\xe0 rest")


def test_mapping_problems_name_missing_and_duplicate_fields() -> None:
    from tieout.ingest.schema import REQUIRED

    full = {h: h for h in REQUIRED}
    assert upload.mapping_problems(full) == []
    full.pop("currency")
    assert any("currency" in p for p in upload.mapping_problems(full))
    full["extra"] = "site"
    assert any("More than one" in p for p in upload.mapping_problems(full))


def test_suggestions_for_renamed_headers() -> None:
    found = to_mapping(upload.suggest_columns(["Plant", "Document Date", "Supplier Name"]))
    assert found["Plant"] == "site"
    assert found["Document Date"] == "doc_date"
    assert found["Supplier Name"] == "vendor_name"


def _mapping(blobs: dict[str, bytes]) -> dict[str, dict[str, str]]:
    return {
        c: to_mapping(upload.suggest_columns(upload.peek_file(b).headers)) for c, b in blobs.items()
    }


def test_check_then_run(blobs: dict[str, bytes]) -> None:
    mapping = _mapping(blobs)
    check = upload.check_upload(blobs["acquirer"], blobs["target"], mapping)
    assert not check.blocked
    assert check.rows["acquirer"] > check.rows["target"] > 0
    assert not check.suggestions.empty and check.spend > 0
    seen: list[str] = []
    results = upload.run_upload(
        blobs["acquirer"],
        blobs["target"],
        mapping,
        check.suggestions,
        names={"acquirer": "buyer.csv", "target": "seller.xlsx"},
        progress=lambda stage, counts: seen.append(stage),
    )
    assert set(results.lines["source_file"]) == {"buyer.csv", "seller.xlsx"}
    assert seen == ["ingest", "vendor_matching", "item_matching", "synergy"]
    assert results.meta["scenario"] == "custom"
    assert results.meta["category_mapping"]["source"] == "supplied"
    assert results.totals


def test_check_blocks_a_missing_required_column(blobs: dict[str, bytes]) -> None:
    target = blobs["target"].replace(b",currency,", b",ccy,", 1)  # header the tool cannot place
    mapping = _mapping({**blobs, "target": target})
    assert "ccy" not in mapping["target"]
    check = upload.check_upload(blobs["acquirer"], target, mapping)
    assert check.blocked
    blocking = check.findings[check.findings["severity"] == "blocking"]
    assert (blocking["rule"] == "required_column_missing").any()
    assert check.suggestions.empty


def test_apply_category_file_sets_known_codes_and_counts_the_rest(
    blobs: dict[str, bytes], small_files
) -> None:
    mapping = _mapping(blobs)
    check = upload.check_upload(blobs["acquirer"], blobs["target"], mapping)
    shipped = small_files["category_map"].read_bytes()
    out, applied, skipped = upload.apply_category_file(check.suggestions, shipped)
    assert applied > 0 and out["l2_code"].notna().sum() >= applied
    extra = shipped + b"acquirer,No such category,L01.01\nacquirer,x,NOPE\n"
    _, _, skipped_extra = upload.apply_category_file(check.suggestions, extra)
    assert skipped_extra == skipped + 2


def test_apply_category_file_needs_its_columns() -> None:
    choices = pd.DataFrame({"company": [], "category_native": [], "spend": [], "l2_code": []})
    with pytest.raises(ValueError, match="needs the columns"):
        upload.apply_category_file(choices, b"a,b\n1,2\n")


def test_category_map_drops_unmapped_rows() -> None:
    choices = pd.DataFrame(
        {
            "company": ["acquirer", "target", "target"],
            "category_native": ["A", "B", "C"],
            "spend": [1.0, 2.0, 3.0],
            "l2_code": ["X", None, ""],
        }
    )
    out = upload.category_map_from(choices)
    assert out.to_dict("records") == [
        {"company": "acquirer", "category_native": "A", "l2_code": "X"}
    ]
