from __future__ import annotations

import re

import pytest

from tieout.reference import (
    load_abbreviations,
    load_column_synonyms,
    load_descriptor_tokens,
    load_fx_rates,
    load_generic_tokens,
    load_taxonomy,
    load_thresholds,
    load_uom,
)

L1_NAMES = [
    "Raw materials & metals",
    "Fasteners & hardware",
    "Bearings & power transmission",
    "Pipe, valves & fittings",
    "Electrical & automation",
    "Abrasives & cutting tools",
    "Safety & PPE",
    "Packaging",
    "Chemicals & lubricants",
    "MRO general & facilities",
    "Logistics & freight",
    "Professional & IT services",
]
COLUMNS_31 = [
    "site", "doc_date", "vendor_id", "vendor_name", "vendor_tax_id", "vendor_country",
    "item_code", "item_description", "mpn", "manufacturer", "category_native", "uom",
    "pack_qty", "quantity", "unit_price", "line_amount", "currency", "payment_terms_days",
    "payment_date", "contract_id", "contract_end_date", "incoterm", "spend_type",
    "po_number", "po_line",
]  # fmt: skip
GENERIC = (
    "industrial industries supply supplies services service national american international "
    "global group solutions products enterprises holdings systems technologies associates "
    "partners distribution distributors trading usa north america"
).split()
DESCRIPTOR = (
    "logistics freight fasteners bearings electric electrical steel metals packaging chemical "
    "chemicals tools tooling safety hydraulics pneumatics plastics rubber valves pumps welding "
    "abrasives lubricants staffing consulting software"
).split()
UOM_CODES = (
    "EA PC UN PR DZ GS GRO C FT IN LB GAL YD MTR CM MM KG G GM OZ T MT L LT ML HR "
    "BX CS PK BG RL DR PL M GR"
).split()


@pytest.fixture(scope="module")
def tax():
    return load_taxonomy()


def test_taxonomy_shape(tax):
    assert list(tax.columns) == [
        "l1_code", "l1_name", "l2_code", "l2_name", "keywords",
        "family", "uom_dimension", "category_type", "criticality",
    ]  # fmt: skip
    assert len(tax) == 60
    assert tax["l2_code"].is_unique
    assert tax["l2_name"].is_unique
    assert list(tax["l1_name"].drop_duplicates()) == L1_NAMES
    assert (tax.groupby("l1_code").size() == 5).all()
    assert tax["l1_code"].nunique() == 12
    assert tax["l2_code"].str.fullmatch(r"L\d\d\.\d\d").all()
    assert (tax["l2_code"].str[:3] == tax["l1_code"]).all()


def test_taxonomy_allowed_values(tax):
    assert set(tax["family"]) <= {
        "fasteners", "bearings", "pvf", "electrical", "ppe", "abrasives", "generic",
    }  # fmt: skip
    assert set(tax["uom_dimension"]) <= {"count", "length", "mass", "volume", "time"}
    assert set(tax["category_type"]) <= {"commodity", "engineered", "mro", "indirect"}
    assert set(tax["criticality"]) <= {"critical", "standard", "non_critical"}
    assert (tax["criticality"] == "critical").sum() >= 6
    assert (tax["criticality"] == "non_critical").sum() >= 10
    # every parser family is used at least once
    assert set(tax["family"]) >= {"fasteners", "bearings", "pvf", "electrical", "ppe", "abrasives"}


def test_taxonomy_indirect_rows(tax):
    last = tax[tax["l1_name"].isin(L1_NAMES[-2:])]
    assert len(last) == 10
    assert (last["category_type"] == "indirect").all()
    assert (last["uom_dimension"] == "time").all()
    assert (last["family"] == "generic").all()
    rest = tax.drop(last.index)
    assert not (rest["category_type"] == "indirect").any()
    assert not (rest["uom_dimension"] == "time").any()


def test_taxonomy_keywords(tax):
    seen: dict[str, str] = {}
    for code, kw in zip(tax["l2_code"], tax["keywords"], strict=True):
        words = kw.split(";")
        assert 8 <= len(words) <= 15, code
        assert len(set(words)) == len(words), code
        for w in words:
            assert w == w.lower().strip() and w, (code, w)
            assert w not in seen, f"{w!r} shared by {seen[w]} and {code}"
            seen[w] = code


def test_abbreviations():
    ab = load_abbreviations()
    assert len(ab) >= 120
    assert ab["BRG"] == "BEARING"
    assert ab["SS"] == "STAINLESS STEEL"
    assert ab["HX"] == "HEX"
    assert ab["ZN"] == "ZINC"
    assert ab["GALV"] == "GALVANIZED"
    for k, v in ab.items():
        assert k == k.upper() and v == v.upper() and k and v
        assert re.fullmatch(r"[A-Z0-9]+", k), k
        assert k != v
        assert k not in UOM_CODES, k
    with open(_ref("abbreviations.csv"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert lines[0] == "abbr,expansion"
    keys = [line.split(",", 1)[0] for line in lines[1:]]
    assert len(keys) == len(set(keys))


def test_token_lists_verbatim():
    assert load_generic_tokens() == frozenset(GENERIC)
    assert load_descriptor_tokens() == frozenset(DESCRIPTOR)
    assert len(GENERIC) == 25 and len(DESCRIPTOR) == 26
    assert _ref("generic_tokens.txt").read_text().split() == GENERIC
    assert _ref("descriptor_tokens.txt").read_text().split() == DESCRIPTOR
    assert not load_generic_tokens() & load_descriptor_tokens()


def test_column_synonyms():
    syn = load_column_synonyms()
    assert list(syn) == COLUMNS_31
    seen: set[str] = set()
    for col, words in syn.items():
        assert 5 <= len(words) <= 12, col
        assert len(set(words)) == len(words), col
        for w in words:
            assert w == w.lower(), (col, w)
            assert w not in seen, f"{w!r} listed twice"
            seen.add(w)


def test_fx_rates():
    assert load_fx_rates() == {"USD": 1.00, "CAD": 0.73, "EUR": 1.08, "GBP": 1.27}
    assert _ref("fx_rates.csv").read_text().splitlines()[0] == "currency,rate"


def test_uom():
    u = load_uom()
    expected = {
        "EA": 1, "PC": 1, "UN": 1, "PR": 2, "DZ": 12, "GS": 144, "GRO": 144, "C": 100,
        "FT": 0.3048, "IN": 0.0254, "LB": 0.45359237, "GAL": 3.785411784, "YD": 0.9144,
        "MTR": 1, "CM": 0.01, "MM": 0.001, "KG": 1, "G": 0.001, "GM": 0.001,
        "OZ": 0.028349523125, "T": 1000, "MT": 1000, "L": 1, "LT": 1, "ML": 0.001, "HR": 1,
    }  # fmt: skip
    assert {k: v.factor for k, v in u.fixed.items()} == expected
    assert u.fixed["EA"].base == "each" and u.fixed["EA"].dimension == "count"
    assert u.fixed["FT"].base == "metre" and u.fixed["FT"].dimension == "length"
    assert u.fixed["LB"].base == "kilogram" and u.fixed["LB"].dimension == "mass"
    assert u.fixed["GAL"].base == "litre" and u.fixed["GAL"].dimension == "volume"
    assert u.fixed["HR"].base == "hour" and u.fixed["HR"].dimension == "time"
    assert u.pack_units == ("BX", "CS", "PK", "BG", "RL", "DR", "PL")
    assert "M" not in u.fixed and "GR" not in u.fixed
    assert not set(u.fixed) & set(u.pack_units)


def test_thresholds():
    t = load_thresholds()
    assert (t.vendor_auto, t.vendor_review) == (92.0, 75.0)
    assert (t.item_auto_cosine, t.item_review_cosine) == (0.80, 0.60)
    assert "overwritten" in _ref("thresholds.toml").read_text()


def test_path_override(tmp_path):
    p = tmp_path / "fx.csv"
    p.write_text("currency,rate\nJPY,0.0067\n")
    assert load_fx_rates(p) == {"JPY": 0.0067}
    g = tmp_path / "g.txt"
    g.write_text("acme\n\nwidget\n")
    assert load_generic_tokens(str(g)) == frozenset({"acme", "widget"})
    th = tmp_path / "t.toml"
    th.write_text(
        "[vendor]\nauto = 90\nreview = 70\n[item]\nauto_cosine = 0.7\nreview_cosine = 0.5\n"
    )
    assert load_thresholds(th).vendor_auto == 90.0


def _ref(name):
    from importlib import resources

    return resources.files("tieout.reference").joinpath(name)
