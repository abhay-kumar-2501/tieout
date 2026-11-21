"""V0 vendor-name normalisation (PRD 4.3), one test per rule."""

import pytest

from tieout.normalise.vendors import (
    normalise_country,
    normalise_tax_id,
    normalise_vendor_name,
)


def name(text: str) -> str:
    return normalise_vendor_name(text).name


def test_nfkc_casefold_and_accents() -> None:
    assert name("ＡＣＭＥ Société Générale") == "acme societe generale"
    assert name("Straße Bau") == "strasse bau"


@pytest.mark.parametrize(
    "text",
    [
        "Acme Inc dba Fastline",
        "Acme Inc d/b/a Fastline",
        "Acme Inc t/a Fastline",
        "ACME D.B.A. Fastline",
    ],
)
def test_dba_names_become_aliases(text: str) -> None:
    result = normalise_vendor_name(text)
    assert result.name == "acme"
    assert result.aliases == ("fastline",)
    assert result.names == ("acme", "fastline")


def test_dba_inside_a_word_is_not_split() -> None:
    assert normalise_vendor_name("Dbase Systems").aliases == ()


@pytest.mark.parametrize(
    ("text", "expected_name", "branch"),
    [
        ("Acme Corp - Chicago", "acme", "chicago"),
        ("Acme Store #12", "acme", "store #12"),
        ("Acme #12", "acme", "#12"),
        ("Acme (Plant 3)", "acme", "plant 3"),
        ("Acme Ltd (DC Atlanta)", "acme", "dc atlanta"),
        ("Acme Whse 4", "acme", "whse 4"),
        ("ACME Corp - Chicago Plant 3", "acme", "chicago plant 3"),
    ],
)
def test_branch_markers_move_to_their_own_field(text: str, expected_name: str, branch: str) -> None:
    result = normalise_vendor_name(text)
    assert (result.name, result.branch) == (expected_name, branch)


@pytest.mark.parametrize("text", ["Coca-Cola Co", "Acme Site Services", "Store Fixtures Inc"])
def test_non_branch_text_is_kept(text: str) -> None:
    assert normalise_vendor_name(text).branch is None


def test_ampersand_punctuation_whitespace_and_leading_the() -> None:
    assert name("The  Smith & Wesson,   Inc.") == "smith and wesson"
    assert name("O'Brien-Jones  Supply") == "obrien jones supply"
    assert name("The") == "the"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Acme Co Ltd", "acme"),
        ("Acme Holdings GmbH AG", "acme holdings"),
        ("Société Générale S.A.", "societe generale"),
        ("Smith & Co.", "smith"),
        ("Company Supply Inc", "company supply"),
        ("Acme Corporation Products", "acme corporation products"),
        ("Ltd", "ltd"),
    ],
)
def test_legal_forms_removed_from_the_end_only_repeatedly(text: str, expected: str) -> None:
    assert name(text) == expected


def test_original_is_kept() -> None:
    assert normalise_vendor_name("The Acme Company, Inc.").original == "The Acme Company, Inc."
    assert normalise_vendor_name(None).name == ""


def test_tax_id_and_country_normalisation() -> None:
    assert normalise_tax_id(" 12-345.678 ab ") == "12345678AB"
    assert normalise_tax_id("--") is None
    assert normalise_tax_id(None) is None
    assert normalise_country(" us ") == "US"
    assert normalise_country("USA") is None
    assert normalise_country("1A") is None
