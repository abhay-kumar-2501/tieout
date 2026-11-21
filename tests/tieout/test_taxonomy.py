import pandas as pd
import pytest

from tieout.normalise.taxonomy import (
    apply_category_map,
    suggest_categories,
    tokenize,
    unmapped_spend,
)
from tieout.reference import load_taxonomy

TAXONOMY = load_taxonomy()


def lines(*rows):
    base = {
        "company": "acquirer",
        "category_native": "Fasteners",
        "item_description": "WIDGET",
        "amount": 100.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def cmap(*rows):
    return pd.DataFrame(rows, columns=["company", "category_native", "l2_code"])


def test_apply_adds_the_taxonomy_attributes():
    out = apply_category_map(
        lines(
            {"category_native": "Bolts"},
            {"category_native": "Cable", "company": "target"},
            {"category_native": "Haulage"},
        ),
        cmap(
            ("acquirer", "Bolts", "L02.01"),
            ("target", "Cable", "L05.01"),
            ("acquirer", "Haulage", "L11.01"),
        ),
        TAXONOMY,
    )
    assert out["l2_code"].tolist() == ["L02.01", "L05.01", "L11.01"]
    assert out["l1_code"].tolist() == ["L02", "L05", "L11"]
    assert out["family"].tolist() == ["fasteners", "electrical", "generic"]
    assert out["uom_dimension"].tolist() == ["count", "length", "time"]
    assert out["category_type"].tolist() == ["commodity", "commodity", "indirect"]


def test_mapping_is_per_company():
    out = apply_category_map(
        lines({"company": "acquirer"}, {"company": "target"}),
        cmap(("acquirer", "Fasteners", "L02.01")),
        TAXONOMY,
    )
    assert out["l2_code"].tolist() == ["L02.01", None]


def test_labels_match_after_trimming_and_case_folding():
    out = apply_category_map(
        lines({"category_native": "  FASTENERS "}),
        cmap(("acquirer", "fasteners", "L02.01")),
        TAXONOMY,
    )
    assert out["l2_code"].tolist() == ["L02.01"]


def test_unmapped_lines_get_none_in_every_attribute():
    out = apply_category_map(lines({}), cmap(("acquirer", "Other", "L02.01")), TAXONOMY)
    for column in ("l1_code", "l2_code", "family", "uom_dimension", "category_type"):
        assert out[column].tolist() == [None]


def test_no_map_leaves_everything_unmapped():
    assert apply_category_map(lines({}), None, TAXONOMY)["l2_code"].tolist() == [None]
    empty = cmap()
    assert apply_category_map(lines({}), empty, TAXONOMY)["l2_code"].tolist() == [None]


def test_unknown_l2_code_is_unmapped():
    out = apply_category_map(lines({}), cmap(("acquirer", "Fasteners", "L99.99")), TAXONOMY)
    assert out["l2_code"].tolist() == [None]
    assert out["family"].tolist() == [None]


def test_last_duplicate_mapping_wins_and_input_is_unchanged():
    frame = lines({})
    out = apply_category_map(
        frame,
        cmap(("acquirer", "Fasteners", "L02.01"), ("acquirer", "Fasteners", "L02.02")),
        TAXONOMY,
    )
    assert out["l2_code"].tolist() == ["L02.02"]
    assert "l2_code" not in frame


def test_tokenize():
    assert tokenize("Hex-Bolt M8x40, A36!") == {"hex", "bolt", "m8x40", "a36"}
    assert tokenize(None) == set()


# ---- suggestions ----------------------------------------------------------

SMALL = pd.DataFrame(
    {
        "l1_code": ["A", "A"],
        "l1_name": ["Alpha group", "Alpha group"],
        "l2_code": ["A.01", "A.02"],
        "l2_name": ["Alpha", "Beta"],
        "keywords": [";".join(f"a{i}" for i in range(10)), ";".join(f"b{i}" for i in range(10))],
    }
)
KEYS = [f"a{i}" for i in range(10)]


def described(label, description, amount=100.0):
    return lines({"category_native": label, "item_description": description, "amount": amount})


def test_suggestion_uses_label_and_descriptions():
    out = suggest_categories(described("a9 widgets", " ".join(KEYS[:3])), SMALL)
    row = out.iloc[0]
    # tokens: a9 widgets a0 a1 a2 (5); keywords 10; intersection 4; union 11
    assert row["score"] == pytest.approx(4 / 11)
    assert (row["l2_code"], row["l2_name"]) == ("A.01", "Alpha")


def test_suggestion_threshold_is_inclusive():
    row = suggest_categories(described("", " ".join(KEYS[:3])), SMALL).iloc[0]
    assert row["score"] == pytest.approx(0.3)  # 3 / 10
    assert row["l2_code"] == "A.01"


def test_below_threshold_is_left_unmapped():
    row = suggest_categories(described("", " ".join(KEYS[:2])), SMALL).iloc[0]
    assert row["score"] == pytest.approx(0.2)
    assert row["l2_code"] is None
    assert row["l2_name"] is None


def test_custom_threshold():
    frame = described("", " ".join(KEYS[:2]))
    assert suggest_categories(frame, SMALL, threshold=0.2).iloc[0]["l2_code"] == "A.01"


def test_only_the_twenty_highest_spend_descriptions_count():
    # 20 big-spend descriptions use 3 keywords between them; one small one holds the rest
    big = [described("", KEYS[i % 3] + "." * (i // 3), 1000.0 - i) for i in range(20)]
    small = [described("", " ".join(KEYS[3:]), 1.0)]
    frame = pd.concat([*big, *small], ignore_index=True)
    assert suggest_categories(frame, SMALL).iloc[0]["score"] == pytest.approx(0.3)
    assert suggest_categories(frame, SMALL, top_descriptions=21).iloc[0]["score"] == pytest.approx(
        1.0
    )


def test_description_spend_is_summed_before_ranking():
    frame = pd.concat(
        [
            described("", "noise", 50.0),
            described("", " ".join(KEYS[:3]), 30.0),
            described("", " ".join(KEYS[:3]), 30.0),
        ],
        ignore_index=True,
    )
    row = suggest_categories(frame, SMALL, top_descriptions=1).iloc[0]
    assert row["l2_code"] == "A.01"  # the repeated description outranks "noise" in total


def test_ties_break_on_l2_code():
    tied = SMALL.copy()
    tied["keywords"] = SMALL.loc[0, "keywords"]
    assert suggest_categories(described("", " ".join(KEYS[:5])), tied).iloc[0]["l2_code"] == "A.01"


def test_real_taxonomy_suggestion():
    keys = TAXONOMY.set_index("l2_code").loc["L05.01", "keywords"].split(";")
    frame = described("Wire and cable", " ".join(keys))
    row = suggest_categories(frame, TAXONOMY).iloc[0]
    assert row["l2_code"] == "L05.01"
    assert row["score"] >= 0.3


def test_suggestions_are_per_company_and_label_sorted_by_spend():
    frame = lines(
        {"category_native": "A", "item_description": "x", "amount": 5.0},
        {"category_native": "B", "item_description": " ".join(KEYS[:5]), "amount": 50.0},
        {"category_native": "B", "company": "target", "item_description": "y", "amount": 1.0},
    )
    out = suggest_categories(frame, SMALL)
    assert out[["company", "category_native"]].values.tolist() == [
        ["acquirer", "B"],
        ["acquirer", "A"],
        ["target", "B"],
    ]
    assert out.loc[0, "l2_code"] == "A.01"
    assert out.loc[0, "spend"] == 50.0
    assert list(out.columns) == [
        "company",
        "category_native",
        "spend",
        "l2_code",
        "l2_name",
        "score",
    ]


def test_suggestions_use_line_amount_when_amount_is_absent():
    frame = lines({"item_description": "x"}).rename(columns={"amount": "line_amount"})
    assert suggest_categories(frame, TAXONOMY).iloc[0]["spend"] == 100.0


# ---- unmapped spend -------------------------------------------------------


def test_unmapped_spend_report():
    frame = lines(
        {"l2_code": "L02.01", "amount": 600.0},
        {"l2_code": None, "category_native": "Mystery", "amount": 300.0},
        {"l2_code": None, "category_native": "Mystery", "amount": 50.0},
        {"l2_code": None, "category_native": "Other", "amount": 50.0},
        {"l2_code": None, "category_native": None, "amount": 10.0, "company": "target"},
    )
    out = unmapped_spend(frame)
    assert out[["company", "category_native", "rows", "amount"]].values.tolist() == [
        ["acquirer", "Mystery", 2, 350.0],
        ["acquirer", "Other", 1, 50.0],
        ["target", "(blank)", 1, 10.0],
    ]
    assert out["share"].tolist() == pytest.approx([0.35, 0.05, 1.0])


def test_unmapped_spend_empty_when_everything_is_mapped():
    out = unmapped_spend(lines({"l2_code": "L02.01"}))
    assert out.empty
    assert list(out.columns) == ["company", "category_native", "rows", "amount", "share"]
