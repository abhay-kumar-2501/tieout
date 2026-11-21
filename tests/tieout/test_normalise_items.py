"""Item normalisation: I0 descriptions, MPNs, manufacturers, MPN-like tokens (PRD 4.4)."""

import pytest

from tieout.normalise.items import (
    extract_mpn_like_tokens,
    is_dimension_token,
    is_valid_mpn,
    item_key,
    manufacturers_compatible,
    mpn_key,
    normalise_description,
    normalise_manufacturer,
    normalise_mpn,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("m8 x 40", "M8X40"),
        ("M8 X 40", "M8X40"),
        ("M8-40", "M8X40"),
        ("M8X40", "M8X40"),
        ("M8-1.25X40", "M8-1.25X40"),
        ("M8 x 1.25 x 40 mm", "M8X1.25X40MM"),
        ('1/4"-20 x 1"', "1/4IN-20X1IN"),
        ("4-1/2 x 1/4 x 7/8", "4-1/2X1/4X7/8"),
        ("10' hose", "10FT HOSE"),
        ("40 MM", "40MM"),
        ("120 VAC  20 A", "120VAC 20A"),
    ],
)
def test_dimension_and_unit_standardisation(raw: str, expected: str) -> None:
    assert normalise_description(raw) == expected


def test_abbreviations_expand_whole_tokens_only() -> None:
    assert normalise_description("brg ball 6204") == "BEARING BALL 6204"
    assert normalise_description("hhcs ss") == "HEX HEAD CAP SCREW STAINLESS STEEL"
    assert normalise_description("SS-304, ZP") == "STAINLESS STEEL-304, ZINC PLATED"
    # Not whole tokens: left alone.
    assert normalise_description("SSX BRGS2 HXA") == "SSX BRGS2 HXA"
    assert normalise_description("SS304") == "SS304"


def test_custom_abbreviations_and_blank() -> None:
    assert normalise_description("ABC def", {"ABC": "ALPHA"}) == "ALPHA DEF"
    assert normalise_description(None) == ""
    assert normalise_description("  ") == ""


@pytest.mark.parametrize(
    ("raw", "norm", "valid"),
    [
        ("6204-2RS", "62042RS", True),
        ("ab-12.c/3", "AB12C3", True),
        ("12345", "12345", True),
        ("AB12", "AB12", False),  # four characters
        ("ABCDEF", "ABCDEF", False),  # no digit
        ("  ", None, False),
        (None, None, False),
    ],
)
def test_mpn_normalisation_and_validity(raw: str | None, norm: str | None, valid: bool) -> None:
    assert normalise_mpn(raw) == norm
    assert is_valid_mpn(norm) is valid
    assert mpn_key(raw) == (norm if valid else None)


def test_manufacturer_v0_normalisation() -> None:
    assert normalise_manufacturer("The Timken Company") == "timken"
    assert normalise_manufacturer("Parker-Hannifin Corp.") == "parker hannifin"
    assert normalise_manufacturer("Société Générale S.A.") == "societe generale"
    assert normalise_manufacturer("Black & Decker Inc") == "black and decker"
    assert normalise_manufacturer(None) == ""


@pytest.mark.parametrize(
    ("a", "b", "compatible"),
    [
        ("SKF", "SKF Inc.", True),  # equal after V0
        ("SKF", None, True),  # blank side
        ("", "Timken", True),
        ("Parker Hannifin", "Hannifin Parker", True),  # token_sort_ratio 100
        ("Grainger Fastenal", "Grainger Fastenl", True),  # ratio >= 90
        ("SKF", "Timken", False),
        ("NSK", "NTN", False),
        ("Apollo Valves", "Apex Valves", False),
    ],
)
def test_manufacturer_compatibility(a: str | None, b: str | None, compatible: bool) -> None:
    assert manufacturers_compatible(a, b) is compatible


def test_item_key() -> None:
    assert item_key("FA-10023", "6204-2RS", "SKF") == "FA-10023"
    assert item_key(None, "6204-2RS", "SKF Inc") == "MPN:62042RS|skf"
    assert item_key("  ", "6204-2RS", None) == "MPN:62042RS|"
    assert item_key(None, None, "SKF") is None


def test_mpn_like_tokens_exclude_dimensions() -> None:
    desc = "CONTACTOR ABB AF09-30-10-13 3P 120VAC M8X40 1/4-20X1 6204-2RS 12345"
    assert extract_mpn_like_tokens(desc) == ["62042RS", "AF09301013"]
    assert extract_mpn_like_tokens(None) == []


@pytest.mark.parametrize(
    "token", ["M8X40", "M8-1.25X40", "1/4-20X1", "120VAC", "4-1/2X7/8", "100X6X22MM", "60GRIT"]
)
def test_dimension_tokens(token: str) -> None:
    assert is_dimension_token(token)


@pytest.mark.parametrize("token", ["AF09-30-10-13", "6204-2RS", "SKU-A1234"])
def test_part_numbers_are_not_dimensions(token: str) -> None:
    assert not is_dimension_token(token)
