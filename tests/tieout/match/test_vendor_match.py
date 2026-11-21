"""Staged vendor matching (PRD 4.3, 10.1), one focused test per rule and guard."""

from __future__ import annotations

import pandas as pd
import pytest
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from tieout.match.review import make_pair_id, record_decision
from tieout.match.vendors import (
    PAIR_COLUMNS,
    VENDOR_MAP_COLUMNS,
    NameScorer,
    build_vendor_records,
    match_vendors,
)


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


def frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def le(result, key: str) -> str:
    vm = result.vendor_map.set_index("vendor_key")
    return str(vm.loc[key, "legal_entity_id"])


def row(result, key: str) -> pd.Series:
    return result.vendor_map.set_index("vendor_key").loc[key]


def pair(result, pair_type: str, a: str, b: str) -> pd.Series:
    pid = make_pair_id(pair_type, a, b)
    hit = result.pairs.loc[result.pairs["pair_id"] == pid]
    assert len(hit) == 1, f"{pid} not in pairs"
    return hit.iloc[0]


def same(result, a: str, b: str) -> bool:
    return le(result, a) == le(result, b)


SCORER = NameScorer()


# ------------------------------------------------------------------ contract


def test_output_columns_follow_the_contract() -> None:
    result = match_vendors(frame(rec("acquirer:V1", "Acme Inc"), rec("target:T1", "ACME Corp")))
    assert list(result.vendor_map.columns) == list(VENDOR_MAP_COLUMNS)
    assert list(result.pairs.columns) == list(PAIR_COLUMNS)


def test_build_vendor_records_takes_most_frequent_values() -> None:
    lines = pd.DataFrame(
        {
            "vendor_key": ["acquirer:V1"] * 3 + ["target:T1"],
            "company": ["acquirer"] * 3 + ["target"],
            "vendor_id": ["V1"] * 3 + ["T1"],
            "vendor_name": ["Acme Inc", "Acme Inc", "ACME", "Bolt Co"],
            "vendor_tax_id": [None, "12", "12", None],
            "vendor_country": ["US", "US", None, "CA"],
            "amount": [10.0, 20.0, 5.0, 1.0],
        }
    )
    records = build_vendor_records(lines)
    first = records.iloc[0]
    assert list(records["vendor_key"]) == ["acquirer:V1", "target:T1"]
    assert (first["vendor_name"], first["vendor_tax_id"], first["vendor_country"]) == (
        "Acme Inc",
        "12",
        "US",
    )
    assert first["spend"] == 35.0


def test_legal_entity_ids_follow_smallest_member_key() -> None:
    result = match_vendors(
        frame(
            rec("target:T2", "Zenith Tools"),
            rec("acquirer:V9", "Bolton Machining"),
            rec("acquirer:V1", "Zenith Tools Inc"),
        )
    )
    assert le(result, "acquirer:V1") == "LE00001"
    assert le(result, "target:T2") == "LE00001"
    assert le(result, "acquirer:V9") == "LE00002"


# ------------------------------------------------------------------ V1


def test_v1_same_tax_id_merges_at_tier_a() -> None:
    result = match_vendors(
        frame(rec("acquirer:V1", "Acme Inc", "12-34"), rec("target:T1", "Zenith Holdings", "1234"))
    )
    assert same(result, "acquirer:V1", "target:T1")
    assert (row(result, "target:T1")["stage"], row(result, "target:T1")["tier"]) == ("V1", "A")
    assert "tax ID 1234" in pair(result, "vendor_match", "acquirer:V1", "target:T1")["evidence"]


def test_v1_same_tax_id_in_different_countries_is_not_evidence() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Acme Inc", "1234", "US"),
            rec("target:T1", "Zenith Holdings", "1234", "CA"),
        )
    )
    assert not same(result, "acquirer:V1", "target:T1")


def test_v1_tax_id_without_country_is_neither_evidence_nor_veto() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Acme Inc", "111", None),
            rec("target:T1", "Acme LLC", "222", "US"),
        )
    )
    assert same(result, "acquirer:V1", "target:T1")
    assert row(result, "target:T1")["stage"] == "V2"


def test_missing_tax_id_falls_through_to_name_stages() -> None:
    result = match_vendors(frame(rec("acquirer:V1", "Acme Inc", "111"), rec("target:T1", "ACME")))
    assert same(result, "acquirer:V1", "target:T1")


def test_different_tax_ids_near_identical_names_are_siblings_not_merged() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Northwind Precision Machining", "111"),
            rec("target:T1", "Northwind Precision Machinng", "222"),
        )
    )
    assert not same(result, "acquirer:V1", "target:T1")
    sibling = pair(result, "vendor_sibling", "acquirer:V1", "target:T1")
    assert sibling["score"] >= 92 and sibling["status"] == "pending"
    assert "sibling" in sibling["evidence"]


def test_veto_on_exact_name_offers_sibling() -> None:
    result = match_vendors(
        frame(rec("acquirer:V1", "Acme Inc", "111"), rec("target:T1", "Acme Corp", "222"))
    )
    assert not same(result, "acquirer:V1", "target:T1")
    assert pair(result, "vendor_sibling", "acquirer:V1", "target:T1")["stage"] == "V2"


def test_vetoed_pair_below_92_is_not_a_sibling() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Northwind Precision Machining", "111"),
            rec("target:T1", "Northwind Precise Machine", "222"),
        )
    )
    sibling_ids = result.pairs.loc[result.pairs["type"] == "vendor_sibling"]
    assert sibling_ids.empty
    assert not same(result, "acquirer:V1", "target:T1")


def test_veto_applies_to_whole_clusters() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Northwind Precision Machining", "111"),
            rec("acquirer:V2", "Northwind Precision Machining"),
            rec("target:T1", "Northwind Precision Machinng", "222"),
        )
    )
    assert same(result, "acquirer:V1", "acquirer:V2")
    assert not same(result, "acquirer:V2", "target:T1")
    blocked = pair(result, "vendor_match", "acquirer:V2", "target:T1")
    assert blocked["status"] == "pending" and blocked["tier"] == "C"
    assert "different tax IDs" in blocked["evidence"]


# ------------------------------------------------------------------ V2


def test_v2_exact_normalised_name_merges_at_tier_a() -> None:
    result = match_vendors(
        frame(rec("acquirer:V1", "The Acme Company, Inc."), rec("target:T1", "ACME Corp - Ohio"))
    )
    assert same(result, "acquirer:V1", "target:T1")
    assert row(result, "target:T1")[["stage", "tier"]].tolist() == ["V2", "A"]


def test_v2_matches_on_dba_alias() -> None:
    result = match_vendors(
        frame(rec("acquirer:V1", "Acme Inc dba Fastline"), rec("target:T1", "Fastline LLC"))
    )
    assert same(result, "acquirer:V1", "target:T1")


def test_v2_group_with_two_tax_ids_in_one_country_is_split() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Acme Inc", "111"),
            rec("acquirer:V2", "Acme Inc", "111"),
            rec("target:T1", "Acme LLC", "222"),
            rec("target:T2", "ACME"),
        )
    )
    assert same(result, "acquirer:V1", "acquirer:V2")  # same tax ID
    assert not same(result, "acquirer:V1", "target:T1")
    assert not same(result, "target:T2", "acquirer:V1")
    assert not same(result, "target:T2", "target:T1")
    assert pair(result, "vendor_sibling", "acquirer:V1", "target:T1")["status"] == "pending"
    for other in ("acquirer:V1", "target:T1"):
        review = pair(result, "vendor_match", other, "target:T2")
        assert (review["status"], review["tier"]) == ("pending", "C")


def test_same_name_different_countries_uses_name_stages() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Acme Inc", "111", "US"), rec("target:T1", "Acme Inc", "222", "CA")
        )
    )
    assert same(result, "acquirer:V1", "target:T1")
    assert row(result, "target:T1")["stage"] == "V2"


# ------------------------------------------------------------------ V3


def test_v3_parent_table_sets_parent_id_without_clustering() -> None:
    parents = pd.DataFrame(
        {
            "key_type": ["name", "tax_id", "tax_id"],
            "key": ["Fastline Inc", "99-1", "77"],
            "country": [None, "US", "CA"],
            "parent_name": ["Acme Holdings Ltd", "Acme Holdings", "Other Group"],
        }
    )
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Zenith dba Fastline"),
            rec("target:T1", "Bolton Machining", "991"),
            rec("target:T2", "Orbit Plastics", "77", "US"),
        ),
        parents,
    )
    assert not same(result, "acquirer:V1", "target:T1")
    assert row(result, "acquirer:V1")["parent_id"] == "P:acme holdings"
    assert row(result, "target:T1")["parent_id"] == "P:acme holdings"
    assert row(result, "target:T1")[["stage", "tier"]].tolist() == ["V3", "A"]
    assert row(result, "target:T2")["parent_id"] == le(result, "target:T2")  # country differs


def test_parent_defaults_to_legal_entity() -> None:
    result = match_vendors(frame(rec("acquirer:V1", "Acme")))
    assert row(result, "acquirer:V1")["parent_id"] == "LE00001"
    assert row(result, "acquirer:V1")[["stage", "tier"]].tolist() == ["none", None]


# ------------------------------------------------------------------ V4 score and guards


def test_v4_score_formula_on_names_without_generic_tokens() -> None:
    a, b = "bolton precision machining supply", "bolton precission machining services"
    stripped_a, stripped_b = "bolton precision machining", "bolton precission machining"
    expected = 0.6 * fuzz.token_sort_ratio(stripped_a, stripped_b) + 40 * (
        JaroWinkler.normalized_similarity(stripped_a, stripped_b)
    )
    assert SCORER.score(a, b).score == pytest.approx(expected, abs=0.01)


def test_token_set_ratio_is_not_used() -> None:
    assert SCORER.score("bolton precision", "bolton precision machining works").score < 92


def test_weak_name_after_generic_removal_is_capped_at_91() -> None:
    result = SCORER.score("acme", "acmee")
    assert result.raw > 91 and result.score == 91
    assert SCORER.score("acme industrial supply", "acme industries").score == 91
    assert SCORER.score("abc de", "abc dee").score == 91  # fewer than six characters


def test_disjoint_descriptors_capped_at_74() -> None:
    result = SCORER.score("northwind tools", "northwind tooling")
    assert result.raw > 74 and result.score == 74
    assert SCORER.score("apex logistics", "apex fasteners").score <= 74


def test_only_one_descriptor_capped_at_91() -> None:
    result = SCORER.score("precision bolton machining", "precision bolton machining tools")
    assert result.raw > 91 and result.score == 91
    assert SCORER.score("apex", "apex logistics").score <= 91


def test_apex_examples_never_auto_match() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Apex Logistics"),
            rec("target:T1", "Apex Fasteners"),
            rec("target:T2", "Apex"),
        )
    )
    assert len(set(result.vendor_map["legal_entity_id"])) == 3


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Bolton Precision", "Bolton Precision Machining"),
        ("Northwind Machining", "Northwind Machining Works Group"),
        ("Apex", "Apex Logistics"),
    ],
)
def test_token_subset_names_never_auto_match(a: str, b: str) -> None:
    result = match_vendors(frame(rec("acquirer:V1", a), rec("target:T1", b)))
    assert not same(result, "acquirer:V1", "target:T1")


def test_thresholds_auto_review_and_none() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Bolton Precision Machining"),
            rec("target:T1", "Bolton Precission Machining"),  # >= 92
            rec("acquirer:V2", "Kestrel Fabrication Works"),
            rec("target:T2", "Kestrel Fabricators Work"),  # 75-92
            rec("acquirer:V3", "Orbit Plastic Molding"),
            rec("target:T3", "Orbit Packaging Lines"),  # < 75
        )
    )
    auto = pair(result, "vendor_match", "acquirer:V1", "target:T1")
    assert (auto["status"], auto["tier"], auto["stage"]) == ("auto", "B", "V4")
    assert row(result, "target:T1")[["stage", "tier"]].tolist() == ["V4", "B"]
    review = pair(result, "vendor_match", "acquirer:V2", "target:T2")
    assert 75 <= review["score"] < 92 and (review["status"], review["tier"]) == ("pending", "C")
    assert not same(result, "acquirer:V2", "target:T2")
    pids = set(result.pairs["pair_id"])
    assert make_pair_id("vendor_match", "acquirer:V3", "target:T3") not in pids


def test_blocking_skips_pairs_without_shared_rare_token_or_prefix() -> None:
    # Similar strings, but no shared token and different first four characters.
    result = match_vendors(
        frame(rec("acquirer:V1", "Kolton Machinery"), rec("target:T1", "Bolton Machinerys"))
    )
    assert result.pairs.empty


def test_every_pair_and_match_carries_evidence() -> None:
    result = match_vendors(
        frame(
            rec("acquirer:V1", "Bolton Precision Machining", "1"),
            rec("target:T1", "Bolton Precission Machining"),
            rec("target:T2", "Kestrel Fabricators Work"),
            rec("acquirer:V2", "Kestrel Fabrication Works"),
            rec("acquirer:V3", "Acme Inc", "1"),
        )
    )
    assert result.pairs["evidence"].str.len().gt(20).all()
    matched = result.vendor_map.loc[result.vendor_map["stage"] != "none"]
    assert matched["evidence"].str.len().gt(10).all()


# ------------------------------------------------------------------ V5


def test_no_chaining_a_b_c_stays_split(monkeypatch: pytest.MonkeyPatch) -> None:
    scores = {
        ("alpha", "bravo"): 95.0,
        ("bravo", "charlie"): 93.0,
        ("alpha", "charlie"): 50.0,
    }
    _patch_scores(monkeypatch, scores)
    result = match_vendors(
        frame(rec("acquirer:A", "Alpha"), rec("target:B", "Bravo"), rec("target:C", "Charlie"))
    )
    assert same(result, "acquirer:A", "target:B")
    assert not same(result, "target:B", "target:C")
    held = pair(result, "vendor_match", "target:B", "target:C")
    assert held["status"] == "pending" and "alpha" in held["evidence"]


def test_names_attached_by_tax_id_are_not_tested(monkeypatch: pytest.MonkeyPatch) -> None:
    scores = {("alpha", "bravo"): 95.0, ("alpha", "zulu"): 10.0, ("bravo", "zulu"): 10.0}
    _patch_scores(monkeypatch, scores)
    result = match_vendors(
        frame(
            rec("acquirer:A", "Alpha", "1"),
            rec("acquirer:Z", "Zulu", "1"),
            rec("target:B", "Bravo"),
        )
    )
    assert same(result, "acquirer:A", "target:B")
    assert same(result, "acquirer:Z", "target:B")


def test_descending_score_order_with_key_tie_break(monkeypatch: pytest.MonkeyPatch) -> None:
    scores = {("alpha", "bravo"): 93.0, ("alpha", "charlie"): 93.0, ("bravo", "charlie"): 60.0}
    _patch_scores(monkeypatch, scores)
    result = match_vendors(
        frame(rec("target:C", "Charlie"), rec("acquirer:A", "Alpha"), rec("target:B", "Bravo"))
    )
    # Tie at 93: (acquirer:A, target:B) sorts before (acquirer:A, target:C).
    assert same(result, "acquirer:A", "target:B")
    assert not same(result, "acquirer:A", "target:C")


def _patch_scores(monkeypatch: pytest.MonkeyPatch, scores: dict[tuple[str, str], float]) -> None:
    """Replace the name scorer and blocking with a fixed score table."""
    from tieout.match import vendors

    def score(self: NameScorer, x: str, y: str) -> vendors.FuzzyScore:
        s = scores.get((min(x, y), max(x, y)), 0.0)
        return vendors.FuzzyScore(s, s, s, s / 100, None)

    def candidates(names, scorer, floor):
        out = []
        for i, x in enumerate(names):
            for j in range(i + 1, len(names)):
                result = scorer.score(x, names[j])
                if result.score >= floor:
                    out.append((i, j, result))
        return out

    monkeypatch.setattr(vendors.NameScorer, "score", score)
    monkeypatch.setattr(vendors, "_candidate_name_pairs", candidates)


NOISY = frame(
    rec("acquirer:V1", "Bolton Precision Machining", "11"),
    rec("target:T1", "Bolton Precission Machining"),
    rec("target:T2", "BOLTON PRECISION MACHINING LLC"),
    rec("acquirer:V2", "Kestrel Fabrication Works"),
    rec("target:T3", "Kestrel Fabricators Work"),
    rec("acquirer:V3", "Northwind Precision Machining", "111"),
    rec("target:T4", "Northwind Precision Machinng", "222"),
    rec("acquirer:V4", "Acme Inc dba Fastline"),
    rec("target:T5", "Fastline LLC"),
    rec("acquirer:V5", "Apex Logistics"),
    rec("target:T6", "Apex Fasteners"),
    rec("target:T7", "Apex"),
    rec("acquirer:V6", "Halvorsen Marine Fittings"),
    rec("target:T8", "Halvorsen Marine Fitting"),
    rec("target:T9", "Halvorsen Marin Fittings Corp"),
)


def test_input_order_independence() -> None:
    base = match_vendors(NOISY)
    for seed in range(5):
        shuffled = NOISY.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        result = match_vendors(shuffled)
        pd.testing.assert_frame_equal(result.vendor_map, base.vendor_map)
        pd.testing.assert_frame_equal(result.pairs, base.pairs)


def test_deterministic_across_runs() -> None:
    first, second = match_vendors(NOISY), match_vendors(NOISY)
    pd.testing.assert_frame_equal(first.vendor_map, second.vendor_map)
    pd.testing.assert_frame_equal(first.pairs, second.pairs)


# ------------------------------------------------------------------ decisions and cache


def _decide(pair_id: str, decision: str, decisions: pd.DataFrame | None = None) -> pd.DataFrame:
    return record_decision(decisions, pair_id, decision, decided_at="2026-01-01T00:00:00Z")


def test_approved_vendor_match_merges_at_tier_a_human() -> None:
    pid = make_pair_id("vendor_match", "acquirer:V2", "target:T3")
    result = match_vendors(NOISY, decisions=_decide(pid, "approve"))
    assert same(result, "acquirer:V2", "target:T3")
    assert row(result, "target:T3")[["stage", "tier"]].tolist() == ["human", "A"]
    assert pair(result, "vendor_match", "acquirer:V2", "target:T3")["status"] == "approved"


def test_rejected_pair_is_never_proposed_or_merged_again() -> None:
    pid = make_pair_id("vendor_match", "acquirer:V1", "target:T1")
    result = match_vendors(NOISY, decisions=_decide(pid, "reject"))
    assert pair(result, "vendor_match", "acquirer:V1", "target:T1")["status"] == "rejected"
    assert not same(result, "acquirer:V1", "target:T1")
    assert result.pairs.loc[result.pairs["pair_id"] == pid, "status"].tolist() == ["rejected"]


def test_approved_sibling_shares_parent_but_stays_separate() -> None:
    pid = make_pair_id("vendor_sibling", "acquirer:V3", "target:T4")
    result = match_vendors(NOISY, decisions=_decide(pid, "approve"))
    assert not same(result, "acquirer:V3", "target:T4")
    pa, pb = row(result, "acquirer:V3")["parent_id"], row(result, "target:T4")["parent_id"]
    assert pa == pb == min(le(result, "acquirer:V3"), le(result, "target:T4"))
    assert pair(result, "vendor_sibling", "acquirer:V3", "target:T4")["status"] == "approved"


def test_rejected_sibling_stays_unrelated() -> None:
    pid = make_pair_id("vendor_sibling", "acquirer:V3", "target:T4")
    result = match_vendors(NOISY, decisions=_decide(pid, "reject"))
    assert row(result, "acquirer:V3")["parent_id"] != row(result, "target:T4")["parent_id"]
    assert pair(result, "vendor_sibling", "acquirer:V3", "target:T4")["status"] == "rejected"


def test_deferred_and_undo() -> None:
    from tieout.match.review import undo_last

    pid = make_pair_id("vendor_match", "acquirer:V2", "target:T3")
    deferred = _decide(pid, "defer")
    assert match_vendors(NOISY, decisions=deferred).pairs.set_index("pair_id").loc[
        pid, "status"
    ] == ("deferred")
    approved = _decide(pid, "approve", deferred)
    undone = undo_last(approved)
    result = match_vendors(NOISY, decisions=undone)
    assert pair(result, "vendor_match", "acquirer:V2", "target:T3")["status"] == "deferred"
    assert not same(result, "acquirer:V2", "target:T3")


@pytest.mark.parametrize("with_decisions", [False, True])
def test_cached_pairs_path_equals_fresh_path(with_decisions: bool) -> None:
    decisions = None
    if with_decisions:
        decisions = _decide(make_pair_id("vendor_match", "acquirer:V2", "target:T3"), "approve")
        decisions = _decide(
            make_pair_id("vendor_sibling", "acquirer:V3", "target:T4"), "approve", decisions
        )
    first = match_vendors(NOISY)
    fresh = match_vendors(NOISY, decisions=decisions)
    cached = match_vendors(NOISY, decisions=decisions, cached_pairs=first.pairs)
    pd.testing.assert_frame_equal(cached.vendor_map, fresh.vendor_map)
    pd.testing.assert_frame_equal(cached.pairs, fresh.pairs)


def test_cached_path_does_not_rescore(monkeypatch: pytest.MonkeyPatch) -> None:
    from tieout.match import vendors

    first = match_vendors(NOISY)

    def boom(*args, **kwargs):
        raise AssertionError("pair scoring re-ran")

    monkeypatch.setattr(vendors, "_candidate_name_pairs", boom)
    match_vendors(NOISY, cached_pairs=first.pairs)
