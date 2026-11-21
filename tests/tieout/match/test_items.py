"""Item records, I1/I3 scoring, one-to-one assembly and review decisions (PRD 4.4, 4.5)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from tieout.match.items import (
    ITEM_MAP_COLUMNS,
    ITEM_RECORD_COLUMNS,
    PAIR_COLUMNS,
    build_item_records,
    match_items,
)

FASTENERS = ("L02.01", "fasteners")


def rec(
    company: str,
    key: str,
    description: str,
    *,
    l2: tuple[str, str] = FASTENERS,
    mpn: str | None = None,
    manufacturer: str | None = None,
    spend: float = 100.0,
) -> dict:
    return {
        "item_record_id": f"{company}:{key}",
        "company": company,
        "item_key": key,
        "item_code": key,
        "mpn": mpn,
        "manufacturer": manufacturer,
        "description": description,
        "l2_code": l2[0],
        "family": l2[1],
        "spend": spend,
    }


def records(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=ITEM_RECORD_COLUMNS)


def pair(result, a: str, b: str) -> pd.Series:
    rows = result.pairs[(result.pairs.key_a == a) & (result.pairs.key_b == b)]
    assert len(rows) == 1, result.pairs[["key_a", "key_b", "status"]]
    return rows.iloc[0]


def partner(result, record_id: str) -> str | None:
    row = result.item_map.set_index("item_record_id").loc[record_id]
    return row["partner_id"]


def decisions(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pair_id": pid,
                "type": "item_match",
                "decision": dec,
                "pack_qty": None,
                "note": None,
                "decided_at": at,
            }
            for pid, dec, at in rows
        ]
    )


# ---------------------------------------------------------------- item records


def _lines() -> pd.DataFrame:
    base = {
        "company": "acquirer",
        "mpn": None,
        "manufacturer": None,
        "l2_code": "L02.01",
        "family": "fasteners",
        "amount": 10.0,
    }
    rows = [
        {**base, "item_code": "FA-1", "item_description": "HHCS M8X40"},
        {**base, "item_code": "FA-1", "item_description": "HHCS M8X40"},
        {**base, "item_code": "FA-1", "item_description": "HEX CAP SCREW M8 X 40 ZP"},
        {**base, "item_code": "FA-2", "item_description": "NUT M8"},
        {**base, "item_code": "FA-2", "item_description": "HEX NUT M8"},
        {**base, "item_code": "FA-3", "item_description": "UNMAPPED", "l2_code": None},
        {**base, "item_code": None, "item_description": "FREIGHT CHARGE"},
        {
            **base,
            "company": "target",
            "item_code": None,
            "mpn": "6204-2RS",
            "manufacturer": "SKF Inc.",
            "item_description": "BRG 6204-2RS",
            "l2_code": "L03.01",
            "family": "bearings",
            "amount": 5.0,
        },
    ]
    return pd.DataFrame(rows)


def test_build_item_records() -> None:
    out = build_item_records(_lines())
    assert list(out.columns) == ITEM_RECORD_COLUMNS
    assert out["item_record_id"].tolist() == [
        "acquirer:FA-1",
        "acquirer:FA-2",
        "target:MPN:62042RS|skf",
    ]
    by_id = out.set_index("item_record_id")
    assert by_id.loc["acquirer:FA-1", "description"] == "HHCS M8X40"  # most frequent
    assert by_id.loc["acquirer:FA-2", "description"] == "HEX NUT M8"  # tie -> longest
    assert by_id.loc["acquirer:FA-1", "spend"] == pytest.approx(30.0)
    assert by_id.loc["target:MPN:62042RS|skf", "family"] == "bearings"
    assert by_id.loc["target:MPN:62042RS|skf", "item_code"] is None


def test_build_item_records_uses_existing_item_key() -> None:
    lines = _lines().assign(item_key=lambda d: d["item_code"])
    out = build_item_records(lines)
    # The MPN-only line has item_key None in this frame, so it is excluded.
    assert out["item_record_id"].tolist() == ["acquirer:FA-1", "acquirer:FA-2"]


def test_blank_descriptions_still_allow_i1() -> None:
    result = match_items(
        records(rec("acquirer", "A1", "", mpn="XY-12345"), rec("target", "T1", "", mpn="XY12345"))
    )
    assert pair(result, "acquirer:A1", "target:T1").tier == "A"


def test_empty_inputs() -> None:
    assert list(build_item_records(pd.DataFrame()).columns) == ITEM_RECORD_COLUMNS
    result = match_items(records())
    assert list(result.item_map.columns) == ITEM_MAP_COLUMNS
    assert list(result.pairs.columns) == PAIR_COLUMNS
    assert result.pairs.empty


# --------------------------------------------------------------------- I1


def test_i1_same_mpn_compatible_manufacturer_is_tier_a() -> None:
    result = match_items(
        records(
            rec(
                "acquirer",
                "A1",
                "BRG BALL 6204",
                l2=("L03.01", "bearings"),
                mpn="6204-2RS",
                manufacturer="SKF",
            ),
            rec(
                "target",
                "T1",
                "DEEP GROOVE BEARING",
                l2=("L03.01", "bearings"),
                mpn="62042RS",
                manufacturer="SKF Inc.",
            ),
        )
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert (row.stage, row.tier, row.status) == ("I1", "A", "auto")
    assert row.pair_id == "item_match|acquirer:A1|target:T1"
    assert "MPN 62042RS" in row.evidence
    assert partner(result, "acquirer:A1") == "target:T1"


def test_i1_incompatible_manufacturers_do_not_match() -> None:
    result = match_items(
        records(
            rec(
                "acquirer",
                "A1",
                "BALL BEARING",
                l2=("L03.01", "bearings"),
                mpn="6204-2RS",
                manufacturer="SKF",
            ),
            rec(
                "target",
                "T1",
                "WIDGET",
                l2=("L03.01", "bearings"),
                mpn="6204-2RS",
                manufacturer="Timken",
            ),
        )
    )
    assert result.pairs.empty
    assert result.item_map["partner_id"].isna().all()


def test_i1_requires_same_l2_and_valid_mpn() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "ALPHA", mpn="XY-12345"),
            rec("target", "T1", "OMEGA", l2=("L02.02", "fasteners"), mpn="XY-12345"),
            rec("acquirer", "A2", "BETA", mpn="AB12"),
            rec("target", "T2", "GAMMA", mpn="AB12"),
        )
    )
    assert result.pairs.empty


def test_i1_with_conflicting_attributes_is_demoted_to_tier_c() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "HHCS M8X40 8.8 ZP", mpn="HX-840-88"),
            rec("target", "T1", "HHCS M8X45 8.8 ZP", mpn="HX84088"),
        )
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert (row.stage, row.tier, row.status) == ("I1", "C", "pending")
    assert "same mpn, conflicting attributes" in row.evidence.lower()
    assert "length 40MM vs 45MM" in row.evidence
    assert partner(result, "acquirer:A1") is None


def test_mpn_like_description_token_is_only_an_i3_candidate() -> None:
    l2 = ("L05.04", "electrical")
    result = match_items(
        records(
            rec("acquirer", "A1", "ABB AF09-30-10-13 CONTACTOR 3P 120V", l2=l2),
            rec("target", "T1", "MAGNETIC STARTER UNIT", l2=l2, mpn="AF09-30-10-13"),
        )
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert (row.stage, row.tier, row.status) == ("I3", "C", "pending")
    assert row.mpn_token == "AF09301013"
    assert row.cosine < 0.60


# --------------------------------------------------------------------- I3


def test_i3_automatic_needs_two_agreeing_attributes() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "HHCS M8 x 40 8.8 ZP"),
            rec("target", "T1", "HHCS M8-40 8.8 ZINC PLT"),
        )
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert row.cosine >= 0.80
    assert (row.stage, row.tier, row.status) == ("I3", "B", "auto")
    assert "thread M8" in row.evidence and "length 40MM" in row.evidence
    assert result.item_map.set_index("item_record_id").loc["target:T1", "tier"] == "B"


def test_i3_conflict_is_vetoed_whatever_the_similarity() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "HHCS M8X40 8.8 ZP"),
            rec("target", "T1", "HHCS M8X45 8.8 ZP"),
        )
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert row.cosine > 0.80
    assert (row.status, row.tier) == ("vetoed", None)
    assert result.item_map["partner_id"].isna().all()


@pytest.mark.parametrize(
    ("family_l2", "desc"),
    [
        (("L10.03", "generic"), "PAPER TOWEL ROLL WHITE"),  # no attributes at all
        (FASTENERS, "WASHER M8"),  # one critical attribute
        (("L09.01", "generic"), "HYD OIL 5GAL"),  # one generic token
    ],
)
def test_text_similarity_alone_never_matches(family_l2: tuple[str, str], desc: str) -> None:
    result = match_items(
        records(rec("acquirer", "A1", desc, l2=family_l2), rec("target", "T1", desc, l2=family_l2))
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert row.cosine == pytest.approx(1.0)
    assert (row.tier, row.status) == ("C", "pending")
    assert "never matches" in row.evidence
    assert result.item_map["partner_id"].isna().all()


def test_generic_subset_is_review_only_and_difference_is_vetoed() -> None:
    l2 = ("L08.03", "generic")
    result = match_items(
        records(
            rec("acquirer", "A1", "STRETCH FILM 18IN X 1500FT 80GA", l2=l2),
            rec("target", "T1", "STRETCH FILM 18IN X 1500FT", l2=l2),
            rec("target", "T2", "STRETCH FILM 18IN X 1500FT 90GA", l2=l2),
        )
    )
    assert pair(result, "acquirer:A1", "target:T1").tier == "C"
    assert pair(result, "acquirer:A1", "target:T1").subset_only
    assert pair(result, "acquirer:A1", "target:T2").status == "vetoed"


def test_unparsed_numbers_that_differ_block_automatic_match() -> None:
    l2 = ("L09.01", "generic")
    result = match_items(
        records(
            rec("acquirer", "A1", "HYD OIL ISO 46 5GAL 40LB", l2=l2),
            rec("target", "T1", "HYD OIL ISO 68 5GAL 40LB", l2=l2),
        )
    )
    row = pair(result, "acquirer:A1", "target:T1")
    assert row.number_mismatch
    assert row.tier == "C"


def test_never_within_one_company_or_across_l2() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "HHCS M8X40 8.8 ZP"),
            rec("acquirer", "A2", "HHCS M8X40 8.8 ZP"),
            rec("target", "T1", "HHCS M8X40 8.8 ZP", l2=("L02.02", "fasteners")),
        )
    )
    assert result.pairs.empty


def test_thresholds_are_inclusive() -> None:
    recs = records(
        rec("acquirer", "A1", "HHCS M8 x 40 8.8 ZP"),
        rec("target", "T1", "HEX CAP SCREW 8.8 ZINC M8X40"),
    )
    first = match_items(recs, auto_cosine=0.999, review_cosine=0.10)
    cosine = pair(first, "acquirer:A1", "target:T1").cosine
    assert pair(first, "acquirer:A1", "target:T1").tier == "C"
    at_auto = match_items(recs, auto_cosine=cosine, review_cosine=0.10)
    assert pair(at_auto, "acquirer:A1", "target:T1").tier == "B"
    at_review = match_items(recs, auto_cosine=0.999, review_cosine=cosine)
    assert pair(at_review, "acquirer:A1", "target:T1").tier == "C"
    above = match_items(recs, auto_cosine=0.999, review_cosine=cosine + 1e-6)
    assert above.pairs.empty


# --------------------------------------------------------------- one-to-one


def test_record_matched_takes_no_further_automatic_match() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "HHCS M8X40 8.8 ZP"),
            rec("target", "T1", "HHCS M8X40 8.8 ZP"),
            rec("target", "T2", "HHCS M8X40 8.8 ZP STEEL"),
        )
    )
    assert pair(result, "acquirer:A1", "target:T1").tier == "B"
    second = pair(result, "acquirer:A1", "target:T2")
    assert (second.tier, second.status) == ("C", "pending")
    assert "acquirer:A1 is already matched to target:T1" in second.evidence
    assert partner(result, "target:T2") is None


def test_ties_are_broken_by_record_key() -> None:
    same = "HHCS M8X40 8.8 ZP"
    result = match_items(
        records(
            rec("acquirer", "A2", same),
            rec("acquirer", "A1", same),
            rec("target", "T2", same),
            rec("target", "T1", same),
        )
    )
    assert partner(result, "acquirer:A1") == "target:T1"
    assert partner(result, "acquirer:A2") == "target:T2"
    assert pair(result, "acquirer:A1", "target:T2").tier == "C"
    assert pair(result, "acquirer:A2", "target:T1").tier == "C"


def test_i1_is_assembled_before_i3() -> None:
    result = match_items(
        records(
            rec("acquirer", "A1", "HHCS M8X40 8.8 ZP", mpn="HX-840"),
            rec("target", "T1", "SCREW HEX", mpn="HX840"),
            rec("target", "T0", "HHCS M8X40 8.8 ZP"),
        )
    )
    assert partner(result, "acquirer:A1") == "target:T1"
    assert pair(result, "acquirer:A1", "target:T1").stage == "I1"
    assert pair(result, "acquirer:A1", "target:T0").tier == "C"


def test_canonical_item_ids() -> None:
    result = match_items(
        records(
            rec("target", "T9", "HHCS M8X40 8.8 ZP"),
            rec("acquirer", "Z1", "HHCS M8X40 8.8 ZP"),
            rec("acquirer", "B1", "BRG 6204", l2=("L03.01", "bearings")),
        )
    )
    ids = result.item_map.set_index("item_record_id")["canonical_item_id"].to_dict()
    assert ids == {
        "acquirer:B1": "CI000001",
        "acquirer:Z1": "CI000002",
        "target:T9": "CI000002",
    }
    attrs = json.loads(result.item_map.set_index("item_record_id").loc["acquirer:B1", "attributes"])
    assert attrs == {"designation": "6204"}


# ---------------------------------------------------------------- decisions


def _review_case() -> pd.DataFrame:
    return records(
        rec("acquirer", "A1", "HHCS M8X40 8.8 ZP"),
        rec("target", "T1", "HHCS M8X40 8.8 ZP"),
        rec("target", "T2", "HHCS M8X40 8.8 ZP STEEL"),
        rec("acquirer", "A3", "WASHER M8"),
        rec("target", "T3", "WASHER M8"),
    )


def test_approved_pair_becomes_tier_a_human() -> None:
    pid = "item_match|acquirer:A3|target:T3"
    result = match_items(_review_case(), decisions=decisions((pid, "approve", "2026-01-01")))
    row = pair(result, "acquirer:A3", "target:T3")
    assert (row.stage, row.tier, row.status) == ("human", "A", "approved")
    item = result.item_map.set_index("item_record_id").loc["target:T3"]
    assert (item.partner_id, item.stage, item.tier) == ("acquirer:A3", "human", "A")


def test_approval_is_blocked_when_a_side_already_has_a_partner() -> None:
    pid = "item_match|acquirer:A1|target:T2"
    result = match_items(_review_case(), decisions=decisions((pid, "approve", "2026-01-01")))
    row = pair(result, "acquirer:A1", "target:T2")
    assert (row.tier, row.status) == ("C", "pending")
    assert "Approval blocked: acquirer:A1 is already matched to target:T1" in row.evidence
    assert partner(result, "acquirer:A1") == "target:T1"


def test_rejected_pair_is_never_proposed_again() -> None:
    pid = "item_match|acquirer:A1|target:T1"
    result = match_items(_review_case(), decisions=decisions((pid, "reject", "2026-01-01")))
    assert pair(result, "acquirer:A1", "target:T1").status == "rejected"
    assert pair(result, "acquirer:A1", "target:T1").tier is None
    # The record is free again, so its next candidate is assembled normally.
    assert partner(result, "acquirer:A1") == "target:T2"


def test_deferred_and_latest_decision_wins() -> None:
    pid = "item_match|acquirer:A3|target:T3"
    result = match_items(
        _review_case(),
        decisions=decisions(
            (pid, "approve", "2026-01-02T10:00:00Z"),
            (pid, "defer", "2026-01-03T10:00:00Z"),
        ),
    )
    assert pair(result, "acquirer:A3", "target:T3").status == "deferred"


def test_approval_of_unproposed_pair_creates_human_match() -> None:
    recs = records(
        rec("acquirer", "A1", "ALPHA WIDGET", l2=("L10.01", "generic")),
        rec("target", "T1", "ZZZ QQQ", l2=("L10.01", "generic")),
    )
    pid = "item_match|acquirer:A1|target:T1"
    result = match_items(recs, decisions=decisions((pid, "approve", "2026-01-01")))
    row = pair(result, "acquirer:A1", "target:T1")
    assert (row.stage, row.tier, row.status) == ("human", "A", "approved")
    assert partner(result, "target:T1") == "acquirer:A1"


def test_every_pair_has_plain_language_evidence() -> None:
    result = match_items(_review_case())
    assert result.pairs["evidence"].str.len().gt(40).all()
    assert result.pairs["evidence"].str.contains("similarity").all()
    assert set(result.pairs["status"]) <= {"auto", "pending", "vetoed"}


# ------------------------------------------------------- caching, determinism


def test_cached_pairs_equal_fresh() -> None:
    recs = _review_case()
    decs = decisions(
        ("item_match|acquirer:A3|target:T3", "approve", "2026-01-01"),
        ("item_match|acquirer:A1|target:T2", "approve", "2026-01-01"),
    )
    fresh = match_items(recs)
    cached = match_items(recs, cached_pairs=fresh.pairs)
    pd.testing.assert_frame_equal(fresh.pairs, cached.pairs)
    pd.testing.assert_frame_equal(fresh.item_map, cached.item_map)

    fresh_dec = match_items(recs, decisions=decs)
    cached_dec = match_items(recs, decisions=decs, cached_pairs=fresh.pairs)
    pd.testing.assert_frame_equal(fresh_dec.pairs, cached_dec.pairs)
    pd.testing.assert_frame_equal(fresh_dec.item_map, cached_dec.item_map)
    again = match_items(recs, decisions=decs, cached_pairs=fresh_dec.pairs)
    pd.testing.assert_frame_equal(fresh_dec.pairs, again.pairs)


def test_cached_pairs_survive_parquet(tmp_path) -> None:
    recs = _review_case()
    fresh = match_items(recs)
    path = tmp_path / "pairs.parquet"
    fresh.pairs.to_parquet(path)
    cached = match_items(recs, cached_pairs=pd.read_parquet(path))
    pd.testing.assert_frame_equal(fresh.item_map, cached.item_map)
    assert fresh.pairs["status"].tolist() == cached.pairs["status"].tolist()


def test_cached_pairs_must_carry_scoring_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        match_items(_review_case(), cached_pairs=pd.DataFrame({"pair_id": []}))


def test_deterministic_under_row_shuffling() -> None:
    recs = pd.concat(
        [
            _review_case(),
            records(
                rec("acquirer", "B1", "BRG 6204-2RS", l2=("L03.01", "bearings")),
                rec("target", "U1", "6204 2RS1 BALL BEARING", l2=("L03.01", "bearings")),
                rec("target", "U2", "6204-ZZ BALL BEARING", l2=("L03.01", "bearings")),
            ),
        ],
        ignore_index=True,
    )
    base = match_items(recs)
    for seed in range(3):
        shuffled = recs.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        result = match_items(shuffled)
        pd.testing.assert_frame_equal(base.pairs, result.pairs)
        pd.testing.assert_frame_equal(base.item_map, result.item_map)
