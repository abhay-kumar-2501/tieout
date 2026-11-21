import pytest

from tieout.normalise.packs import parse_pack_qty, strip_pack_tokens


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("HEX BOLT M8X40 ZINC BOX OF 12", 12),
        ("hex bolt m8x40 bx 100", 100),
        ("NITRILE GLOVE LG CASE OF 1000", 1000),
        ("CUT-OFF WHEEL 4.5IN 25/BX", 25),
        ("CUT-OFF WHEEL 4.5IN BX/25", 25),
        ("WASHER M10 50 PER BOX", 50),
        ("WASHER M10 50 PR PACK", 50),
        ("SAFETY GLASSES CLEAR 12 PC/CS", 12),
        ("SAFETY GLASSES CLEAR 12EA BX", 12),
        ("ZIP TIE 8IN PKG 100", 100),
    ],
)
def test_documented_patterns_are_parsed(description, expected):
    assert parse_pack_qty(description) == expected


@pytest.mark.parametrize(
    "description",
    [
        "HEX BOLT M8X40 ZINC",
        "BOX OF 1",
        "BOX OF 20000",
        "INBOX 12",
        "BEARING 6204-2RS",
        "",
        None,
    ],
)
def test_other_text_is_not_parsed(description):
    assert parse_pack_qty(description) is None


def test_first_pattern_wins():
    assert parse_pack_qty("BOX OF 12 6/CS") == 12


def test_out_of_range_match_falls_through_to_next_pattern():
    assert parse_pack_qty("BOX OF 1 24/CS") == 24


def test_strip_removes_only_the_pack_phrase():
    assert strip_pack_tokens("HEX BOLT M8X40 BOX OF 12 ZINC") == "HEX BOLT M8X40 ZINC"
    assert strip_pack_tokens("HEX BOLT M8X40") == "HEX BOLT M8X40"
    assert strip_pack_tokens(None) == ""
