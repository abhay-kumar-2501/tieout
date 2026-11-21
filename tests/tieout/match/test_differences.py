"""The unexplained-difference guard on automatic item matches, and its wiring."""

from __future__ import annotations

import pandas as pd
import pytest

from tieout.match.differences import unexplained_tokens
from tieout.match.items import ITEM_RECORD_COLUMNS, match_items
from tieout.normalise.items import normalise_description
from tieout.normalise.spelling import is_abbreviation, is_typing_slip


def diff(a: str, b: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return unexplained_tokens(normalise_description(a), normalise_description(b))


@pytest.mark.parametrize(
    ("short", "long", "expected"),
    [
        ("SNDG", "SANDING", True),
        ("CRBD", "CARBIDE", True),
        ("DSC", "DISC", True),
        ("ROLR", "ROLLER", True),
        ("SOOW", "SEOOW", False),  # different cable types, not an abbreviation
        ("SANDING", "SNDG", False),
        ("BRG", "ABRG", False),
    ],
)
def test_is_abbreviation(short: str, long: str, expected: bool) -> None:
    assert is_abbreviation(short, long) is expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("saefty", "safety", True),  # swapped neighbours
        ("fittondren", "fitondren", True),  # doubled letter
        ("supply", "suply", True),  # dropped letter
        ("gilthali", "gilthalt", False),  # substituted letter: a different word
        ("abc", "abc", False),
    ],
)
def test_is_typing_slip(a: str, b: str, expected: bool) -> None:
    assert is_typing_slip(a, b) is expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("BALL BEARING 6805-2Z", "BRG,BALL,6805 2Z"),
        ("TIMING BELT 14M 920 20MM", "BELT,TIMING,920,14M,20MM"),
        ("BALL VALVE 1/2IN 300# BRZ", 'VALVE,BALL,CL300,1/2",BRZ'),
        ("SNDG BELT 4X36 36 GRIT", "SANDING BELT 4X36 36 GRIT"),
        ("WASHER YELLOW ZINC 1/2", "WASHER YZN 1/2"),
        ("CIRCUIT BREAKER 3P 15A", "BRKR,CIRCUIT,3POLE,15A"),
        ("THERMOCOUPLE 3IN 1/4NPT", "THERMOCOUPLE 3IN 1/4NP"),  # field cut short
        ("DRILL BIT HSS TIN 118 DEG", "DRILL BIT HSS 118 DEG"),  # omission only
    ],
)
def test_renderings_of_the_same_good_leave_at_most_one_side(a: str, b: str) -> None:
    only_a, only_b = diff(a, b)
    assert not (only_a and only_b), (only_a, only_b)


@pytest.mark.parametrize(
    ("a", "b", "left", "right"),
    [
        ("DRILL BIT HSS TIN", "DRILL BIT HSS BLACK OXIDE", "TIN", "BLACK"),
        ("SANDING DISC 5IN PSA NO HOLE", 'DISC,SNDG,5",PSA,5 HOLE', "NO", "5"),
        ("HEX NUT M10 CL8 ZP", "NUT,HX,M10,CL10 ZP", "CL8", "CL10"),
        ("HOSE 3/4IN 100R13", "HOSE 3/4IN 100R12", "R13", "R12"),
        ("PORTABLE CORD SOOW 12/3", "CORD,PORTABLE,SEOOW,12/3", "SOOW", "SEOOW"),
        ("RIVET AL/BR 1/8", "RIVET AL/AL 1/8", "AL/BR", "AL/AL"),
    ],
)
def test_two_sided_differences_are_found(a: str, b: str, left: str, right: str) -> None:
    only_a, only_b = diff(a, b)
    assert left in only_a and right in only_b


def _records(desc_a: str, desc_b: str) -> pd.DataFrame:
    rows = [
        ("acquirer", "A1", desc_a),
        ("target", "T1", desc_b),
    ]
    return pd.DataFrame(
        [
            {
                "item_record_id": f"{c}:{k}",
                "company": c,
                "item_key": k,
                "item_code": k,
                "mpn": None,
                "manufacturer": None,
                "description": d,
                "l2_code": "L06.03",
                "family": "abrasives",
                "spend": 100.0,
            }
            for c, k, d in rows
        ],
        columns=ITEM_RECORD_COLUMNS,
    )


def test_two_sided_difference_sends_a_strong_pair_to_review() -> None:
    result = match_items(
        _records("JOBBER DRILL BIT 10MM HSS TIN 118 DEG", "BIT,DRILL JOBBER,10MM,HSS BLKOX,118 DEG")
    )
    row = result.pairs.iloc[0]
    assert row["word_mismatch"] and row["tier"] == "C" and row["status"] == "pending"
    assert "states something the other does not" in row["evidence"]
    assert result.item_map["partner_id"].isna().all()


def test_cached_pairs_must_carry_the_new_column() -> None:
    first = match_items(_records("JOBBER DRILL 10MM HSS TIN", "BIT,DRILL JOBBER,10MM,HSS BLKOX"))
    with pytest.raises(ValueError, match="word_mismatch"):
        match_items(
            _records("JOBBER DRILL 10MM HSS TIN", "BIT,DRILL JOBBER,10MM,HSS BLKOX"),
            cached_pairs=first.pairs.drop(columns="word_mismatch"),
        )
