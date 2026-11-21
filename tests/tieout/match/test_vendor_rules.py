"""Vendor rules added after measuring on the tuning seeds (BUILD_NOTES "Accuracy tuning")."""

from __future__ import annotations

import pandas as pd
import pytest

from tieout.match.review import make_pair_id
from tieout.match.vendors import NameScorer, match_vendors
from tieout.normalise.vendors import normalise_vendor_name


def rec(key: str, name: str, tax: str | None = None, country: str | None = "US") -> dict:
    company, vendor_id = key.split(":")
    return {
        "vendor_key": key,
        "company": company,
        "vendor_id": vendor_id,
        "vendor_name": name,
        "vendor_tax_id": tax,
        "vendor_country": country,
        "spend": 100.0,
    }


def run(*rows: dict, **kwargs: float) -> pd.DataFrame:
    return match_vendors(pd.DataFrame(list(rows)), **kwargs).vendor_map.set_index("vendor_key")


def same(vm: pd.DataFrame, a: str, b: str) -> bool:
    return vm.loc[a, "legal_entity_id"] == vm.loc[b, "legal_entity_id"]


# ------------------------------------------------------------------ V0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Drilon Facility Services Incor", "drilon facility services"),
        ("Venokalon Metal Service Corpor", "venokalon metal service"),
        ("Somarapu Industrial Supply Com", "somarapu industrial supply"),
        ("Halevve Incorporaetd", "halevve"),
        ("Deltsev Electric Liimted", "deltsev electric"),
        ("Acme Comet", "acme comet"),
    ],
)
def test_cut_and_misspelt_legal_forms_are_removed(text: str, expected: str) -> None:
    assert normalise_vendor_name(text).name == expected


def test_an_unclosed_parenthesis_is_a_cut_branch_note() -> None:
    result = normalise_vendor_name("Dogrebri Lubricants Co (PLANT")
    assert (result.name, result.branch) == ("dogrebri lubricants", "plant")


def test_a_cut_name_drops_an_unreadable_final_fragment() -> None:
    assert normalise_vendor_name("Belirki Pallet International A", cut=True).name == (
        "belirki pallet international"
    )
    assert normalise_vendor_name("Puratri Consulting Products In", cut=True).name == (
        "puratri consulting products"
    )
    assert normalise_vendor_name("Belirki Pallet International A").name.endswith(" a")


# ------------------------------------------------------------------ scorer


def test_generic_and_descriptor_words_are_read_through_abbreviations_and_slips() -> None:
    scorer = NameScorer()
    assert scorer.prepare("zidala brgs").text == "zidala bearings"
    assert scorer.prepare("niramara saefty products").text == "niramara safety"
    assert scorer.prepare("rustfavik staffing intl").tokens == ("rustfavik", "staffing")
    assert scorer.score("halundtro elec", "halundtro electric").score == 100.0


def test_distinctive_words_may_differ_only_by_a_typing_slip() -> None:
    scorer = NameScorer()
    assert scorer.distinctive_difference("fittondren freight", "fitondren freight") is None
    assert scorer.distinctive_difference("acme widgets", "acme widg") is None
    assert scorer.distinctive_difference("gilthali coatings", "gilthalt coatings") == (
        "gilthali vs gilthalt"
    )


# ------------------------------------------------------------------ matching


def test_a_substituted_letter_in_the_brand_goes_to_review() -> None:
    result = match_vendors(
        pd.DataFrame(
            [
                rec("acquirer:V1", "Gilthali Coatings Systems Co"),
                rec("target:T1", "GILTHALT COATINGS SYSTEMS CO"),
            ]
        )
    )
    vm = result.vendor_map.set_index("vendor_key")
    assert not same(vm, "acquirer:V1", "target:T1")
    pair = result.pairs.set_index("pair_id").loc[
        make_pair_id("vendor_match", "acquirer:V1", "target:T1")
    ]
    assert pair["status"] == "pending" and "typing slip" in pair["evidence"]


def test_a_slip_in_the_first_letters_is_still_blocked_and_merged() -> None:
    vm = run(rec("acquirer:V1", "Fittondren Freight Corp"), rec("target:T1", "FITONDREN FREIGHT"))
    assert same(vm, "acquirer:V1", "target:T1")
    assert vm.loc["target:T1", "stage"] == "V4"


def test_weak_names_stay_in_review_below_the_cap() -> None:
    # One distinctive word left: capped at 91, review at most, even at a tuned 85.
    vm = run(rec("acquirer:V1", "Groxsom Inc"), rec("target:T1", "GROXOSM INC"), auto_threshold=85)
    assert not same(vm, "acquirer:V1", "target:T1")


def test_names_cut_at_the_field_length_merge_with_their_full_form() -> None:
    target = [
        "BELIRKI PALLET INTERNATIONAL A",
        "DALADRAV HARDWARE INDUSTRIES C",
        "PESTCORAX MAINTENANCE SUPPLY C",
    ]
    assert {len(n) for n in target} == {30}
    vm = run(
        rec("acquirer:V1", "Belirki Pallet International AG", country="DE"),
        rec("target:T1", target[0], country="DE"),
        rec("target:T2", target[1]),
        rec("target:T3", target[2]),
    )
    assert same(vm, "acquirer:V1", "target:T1")
    assert vm.loc["target:T1", "stage"] == "V2"
