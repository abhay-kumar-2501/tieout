"""Truth files agree with the generated inputs (PRD 4.7, 5.2)."""

import re
import unicodedata

import pandas as pd
import pytest

from synthetic.config import COMPANIES
from tieout.normalise.packs import parse_pack_qty

FIXED = {
    "EA": 1.0,
    "PC": 1.0,
    "PR": 1.0,
    "FT": 0.3048,
    "LB": 0.45359237,
    "GAL": 3.785411784,
    "M": 1.0,
    "MTR": 1.0,
    "KG": 1.0,
    "L": 1.0,
    "LT": 1.0,
}
FX = {"USD": 1.0, "CAD": 0.73, "EUR": 1.08}
LEGAL = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "llc",
    "ltd",
    "limited",
    "gmbh",
}


def _norm_name(name: str) -> str:
    """Independent re-implementation of PRD 4.3 V0 for the names the generator uses."""
    text = unicodedata.normalize("NFKC", name).casefold().replace("&", " and ")
    tokens = re.sub(r"[^\w\s]", "", text).split()
    while len(tokens) > 1 and tokens[-1] in LEGAL:
        tokens.pop()
    return " ".join(tokens)


def _keys(df: pd.DataFrame) -> pd.Series:
    coded = df["item_code"] != ""
    mpn = df["mpn"].str.upper().str.replace(r"[^0-9A-Z]", "", regex=True)
    mfr = df["manufacturer"].map(lambda m: _norm_name(m) if m else "")
    return df["item_code"].where(coded, "MPN:" + mpn + "|" + mfr)


def test_every_truth_vendor_exists_and_every_vendor_has_truth(small):
    truth = small.truth_vendor_map
    for company in COMPANIES:
        ids = set(small.purchase_lines(company)["vendor_id"])
        assert set(truth.loc[truth["company"] == company, "vendor_id"]) == ids
    assert not truth.duplicated(["company", "vendor_id"]).any()


def test_every_truth_item_key_exists_and_every_record_has_truth(small):
    truth = small.truth_item_map
    for company in COMPANIES:
        df = small.purchase_lines(company)
        coded = df[(df["item_code"] != "") | (df["mpn"] != "")]
        assert set(truth.loc[truth["company"] == company, "item_key"]) == set(_keys(coded))
    assert not truth.duplicated(["company", "item_key"]).any()


def test_savings_items_are_known_and_shared_items_are_on_both_sides(small):
    sav, items = small.truth_savings, small.truth_item_map
    assert set(sav["true_item_id"]) <= set(items["true_item_id"])
    shared = sav[sav["cause"] != "near_identical"]["true_item_id"]
    per_item = (
        items[items["true_item_id"].isin(shared)].groupby("true_item_id")["company"].nunique()
    )
    assert (per_item == 2).all() and len(per_item) == len(small.world.shared)
    assert (sav["true_gross_gap_usd"] >= 0).all()
    assert set(sav["cause"]) <= {
        "price_gap_same_vendor",
        "price_gap_switch",
        "none",
        "unit_trap",
        "freight_terms",
        "near_identical",
    }
    assert (
        sav.loc[sav["cause"].isin(["freight_terms", "near_identical"]), "true_gross_gap_usd"]
        .eq(0)
        .all()
    )
    assert sav["is_unit_trap"].sum() == small.config.count(small.config.unit_trap_count)


def test_true_gap_matches_lever1_definition_on_visible_data(small):
    """Recompute the gap from the written columns for items without packs or traps."""
    sav = small.truth_savings.set_index("true_item_id")
    plain = [
        s
        for s in small.world.shared
        if not any(h.pack_size or h.trap for h in (s.acquirer, s.target))
        and s.cause.startswith("price")
    ]
    assert len(plain) > 50
    prices = {}
    for company in COMPANIES:
        df = small.lines[company]
        df = df[df["_kind"].isin(["item", "return"])]
        usd = df["line_amount"] * df["currency"].map(FX)
        base = df["quantity"] * df["uom"].map(FIXED)
        g = pd.DataFrame({"item": df["_item"], "usd": usd, "base": base}).groupby("item").sum()
        prices[company] = g
    for s in plain:
        a, t = prices["acquirer"].loc[s.item.item_id], prices["target"].loc[s.item.item_id]
        pa, pt = a["usd"] / a["base"], t["usd"] / t["base"]
        hi_qty = a["base"] if pa >= pt else t["base"]
        assert sav.loc[s.item.item_id, "true_gross_gap_usd"] == pytest.approx(
            abs(pa - pt) * hi_qty, rel=1e-6, abs=0.01
        )


def test_pack_sizes_in_text_parse_with_engine_patterns(small):
    for company in COMPANIES:
        for v in small.items[company]:
            h = v.holding
            parsed = parse_pack_qty(v.description)
            if h.pack_size and h.pack_mode == "text" and not h.trap:
                assert parsed == h.pack_size, v.description
            elif v.uom in {"BX", "CS", "PK"} and h.pack_mode != "text":
                assert parsed is None, v.description
            if h.pack_mode == "column" and not h.trap:
                assert v.pack_qty == h.pack_size


def test_unit_traps_and_memorable_trap(small):
    ds = small
    star = next(s for s in ds.world.shared if s.item.item_id == ds.world.memorable_trap)
    assert star.target.trap == "unconverted" and star.target.pack_size == 12
    assert star.target.spend == pytest.approx(1.2e6 * ds.config.scale)
    traps = [s for s in ds.world.shared if s.distractor == "unit_trap"]
    for s in traps:
        side = s.acquirer if s.acquirer.trap else s.target
        assert side.pack_size >= 4 and side.trap in {"as_each", "unconverted"}


def test_concentration_category_is_dominated_below_cap(small):
    l2 = small.config.concentration_l2
    held = total = 0.0
    for company in COMPANIES:
        df = small.lines[company]
        df = df[df["_l2"] == l2]
        total += df["_usd"].sum()
        held += df.loc[df["_parent"] == small.world.concentration_parent, "_usd"].sum()
    assert 0.35 <= held / total < 0.60
