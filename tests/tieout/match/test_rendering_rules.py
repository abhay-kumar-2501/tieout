"""Rendering rules added after measuring on the tuning seeds (BUILD_NOTES "Accuracy tuning")."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from tieout.match.attributes import numeric_tokens, parse_description
from tieout.match.items import ITEM_RECORD_COLUMNS, match_items
from tieout.normalise.items import manufacturers_compatible, normalise_description
from tieout.normalise.truncation import cut_length

# ------------------------------------------------------------------ I0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BELT,TIMING,920,14M,20MM", "BELT TIMING 920 14M 20MM"),
        ("PIPE 1 1/2 IN SCH 40", "PIPE 1-1/2IN SCHEDULE 40"),
        ('ELBOW,90,3/4",CS', "ELBOW 90 3/4IN CS"),
        ("HOSE -4 1/4IN", "HOSE -4 1/4IN"),
    ],
)
def test_separators_and_mixed_numbers(raw: str, expected: str) -> None:
    assert normalise_description(raw) == expected


def test_a_comma_never_joins_two_numbers() -> None:
    assert numeric_tokens(normalise_description('ELBOW,90,3/4"')) == frozenset({"0.75IN"})
    assert "0.625IN" in numeric_tokens(normalise_description("SPROCKET,13T,#60,5/8IN BORE"))


# ------------------------------------------------------------------ parsers


def test_bearing_inch_bore_reads_the_same_with_a_space_or_a_hyphen() -> None:
    hyphen = parse_description("MOUNTED BEARING UNIT UCF206-31", "bearings")
    space = parse_description("UNIT,MTD BRG,UCF206 31", "bearings")
    assert hyphen["suffix"] == space["suffix"] == "-31"
    assert parse_description("UCF206-24", "bearings") != hyphen


def test_abrasive_diameter_does_not_depend_on_word_order() -> None:
    a = parse_description("BANDSAW BLADE BI-METAL 111IN 1-1/4IN 8/12 TPI", "abrasives")
    b = parse_description('BLADE,BANDSAW BI-METAL,1-1/4",111IN,8/12 TPI', "abrasives")
    assert a["diameter"] == b["diameter"] == "111IN"


def test_abrasive_depth_is_not_a_diameter() -> None:
    a = parse_description("HOLE SAW BI-METAL 1-1/4IN 1-1/2IN DEEP", "abrasives")
    b = parse_description('SAW,HOLE BI-METAL,1-1/2IN DEEP,1-1/4"', "abrasives")
    assert a["diameter"] == b["diameter"] == "1.25IN"


def test_ppe_size_code_is_not_a_numeric_size() -> None:
    assert parse_description("COVERALL DISPOSABLE SZ 2XL", "ppe")["size"] == "2XL"
    assert parse_description("GLOVE NITRILE SZ 9", "ppe")["size"] == "9"


# ------------------------------------------------------------------ manufacturers


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Prestva Bearing Ltd", "PRESTVA", True),
        ("Alestuv Electric Corp", "ALESTUV ELEC", True),
        ("Tovmare Bearing Inc", "TOVMARE BRG", True),
        ("Acme Tools", "Apex Tools", False),
        ("Prestva Bearing", "Bearing Prestva Works", False),
    ],
)
def test_manufacturer_short_forms(a: str, b: str, expected: bool) -> None:
    assert manufacturers_compatible(a, b) is expected


# ------------------------------------------------------------------ cut fields


def test_cut_length_detects_a_pile_up_at_the_limit() -> None:
    cut = ["A" * 10] * 3 + ["B" * 7, "C" * 4]
    assert cut_length(cut) == 10
    assert cut_length(["A" * 10, "B" * 7, "C" * 4]) is None
    assert cut_length([None, "  "]) is None


def _record(company: str, key: str, description: str, mpn: str | None = None) -> dict:
    return {
        "item_record_id": f"{company}:{key}",
        "company": company,
        "item_key": key,
        "item_code": key,
        "mpn": mpn,
        "manufacturer": None,
        "description": description,
        "l2_code": "L04.03",
        "family": "pvf",
        "spend": 100.0,
    }


def test_a_cut_final_token_is_not_read_as_an_attribute() -> None:
    # Three target descriptions sit at 29 characters, so the field was cut there
    # and "SCH 8" may be the start of "SCH 80".
    cut = "FLG WELD NECK 2IN CL150 SCH 8"
    fillers = ("TEE 1IN CL150 SW CS A105 THRD", "CAP 2IN CL300 SW CS A105 THRD")
    assert {len(cut), *map(len, fillers)} == {29}
    records = pd.DataFrame(
        [
            _record("acquirer", "A1", "WELD NECK FLANGE 2IN 150# SCH 80", mpn="WN150280X"),
            _record("target", "T1", cut, mpn="WN150280X"),
            _record("target", "T2", fillers[0]),
            _record("target", "T3", fillers[1]),
        ],
        columns=ITEM_RECORD_COLUMNS,
    )
    result = match_items(records)
    row = result.item_map.set_index("item_record_id").loc["target:T1"]
    assert row["partner_id"] == "acquirer:A1" and row["tier"] == "A"
    assert "schedule" not in json.loads(row["attributes"])
