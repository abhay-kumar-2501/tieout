import time

import numpy as np
import pandas as pd
import pytest
from ingest_fixtures import CATEGORY_MAP, FX

from tieout.ingest import prepare
from tieout.reference import load_taxonomy

ROWS = [
    {"item_code": "FA-1", "po_line": "1"},
    {"item_code": None, "mpn": " ab-12/3 ", "manufacturer": "  ACME Corp ", "po_line": "2"},
    {"item_code": None, "mpn": "ab 123", "manufacturer": None, "po_line": "3"},
    {"item_code": None, "po_line": "4", "category_native": "Freight", "uom": None},
    {"item_code": "FA-9", "mpn": "X1", "po_line": "5"},
    {"item_code": None, "mpn": "---", "po_line": "6", "category_native": "Freight", "uom": None},
]


def test_item_keys_follow_the_identifier_format(run):
    lines = run(ROWS).lines
    acq = lines[lines["company"] == "acquirer"].set_index("po_line")
    assert acq["item_key"].tolist() == [
        "FA-1",
        "MPN:AB123|acme corp",
        "MPN:AB123|",
        None,
        "FA-9",
        None,
    ]
    assert acq.loc["4", "conv_status"] == "none"


def test_not_item_addressable_spend(run):
    p = run(ROWS, period_end="2024-03")
    meta = p.meta["not_item_addressable"]
    assert meta["rows"] == {"acquirer": 2, "target": 2}
    assert meta["amount"]["acquirer"] == pytest.approx(2 * 50 * 12)
    assert meta["share"]["acquirer"] == pytest.approx(2 / 6)
    hit = p.data_quality.query("rule == 'not_item_addressable' and company == 'acquirer'").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("info", 2)
    assert (p.lines.loc[p.lines["item_key"].isna(), "price_exclusion"] == "no_item").all()
    assert not p.lines.loc[p.lines["item_key"].isna(), "price_comparable"].any()


def test_in_scope_and_addressable_spend(run):
    acq = [
        {"category_native": "Fasteners", "line_amount": "50"},
        {"category_native": "Freight", "item_code": None, "uom": None, "po_line": "2"},
        {"category_native": "Mystery", "po_line": "3"},
    ]
    tgt = [{"category_native": "Fasteners", "line_amount": "70", "unit_price": "7"}]
    p = run(acq, tgt, period_end="2024-03")
    assert p.meta["in_scope_spend"] == {
        "acquirer": pytest.approx(150 * 12),
        "target": pytest.approx(70 * 12),
        "total": pytest.approx(220 * 12),
    }
    # only fasteners has spend at both companies; unmapped spend is in scope, not addressable
    assert p.meta["addressable_l2"] == ["L02.01"]
    assert p.meta["addressable_spend"]["acquirer"] == pytest.approx(50 * 12)
    assert p.meta["addressable_spend"]["target"] == pytest.approx(70 * 12)
    assert p.meta["unmapped_spend"]["acquirer"] == pytest.approx(50 * 12)
    rows = p.data_quality.query("rule == 'unmapped_category' and company == 'acquirer'")
    assert rows["rows"].iloc[0] == 1
    assert rows["amount"].iloc[0] == pytest.approx(50 * 12)
    assert p.meta["unmapped_by_category"][0]["category_native"] == "Mystery"


def test_category_attributes_are_added(run):
    p = run([{"category_native": "fasteners "}, {"category_native": "Freight", "po_line": "2"}])
    acq = p.lines[p.lines["company"] == "acquirer"]
    assert acq["l2_code"].tolist() == ["L02.01", "L11.01"]
    assert acq["l1_code"].tolist() == ["L02", "L11"]
    assert acq["uom_dimension"].tolist() == ["count", "time"]
    assert acq["family"].tolist() == ["fasteners", "generic"]


def test_unknown_l2_code_in_category_map_is_a_warning(run):
    bad = pd.concat(
        [
            CATEGORY_MAP,
            pd.DataFrame(
                {"company": ["acquirer"], "category_native": ["Mystery"], "l2_code": ["L99.99"]}
            ),
        ]
    )
    p = run([{"category_native": "Mystery"}], category_map=bad)
    hit = p.data_quality.query("rule == 'unknown_l2_code'").iloc[0]
    assert hit["severity"] == "warning"
    assert p.lines["l2_code"].isna().all()


def test_prepare_without_a_category_map_leaves_everything_unmapped(run):
    p = run([{}], category_map=None)
    assert p.lines["l2_code"].isna().all()
    assert p.meta["addressable_spend"]["total"] == 0


def test_unit_conversion_is_applied_with_pack_paths(run):
    rows = [
        {"uom": "BX", "pack_qty": "50", "po_line": "1"},
        {"uom": "BX", "item_description": "HEX BOLT BOX OF 12", "po_line": "2"},
        {"uom": "BX", "po_line": "3"},
        {"uom": "DZ", "po_line": "4"},
    ]
    p = run(rows, period_end="2024-03")
    acq = p.lines[p.lines["company"] == "acquirer"].set_index("po_line")
    assert acq["conv_status"].tolist() == ["confirmed", "parsed", "unconverted", "confirmed"]
    assert acq["base_factor"].fillna(-1).tolist() == [50, 12, -1, 12]
    assert acq.loc["1", "price_base"] == pytest.approx(5 / 50)
    assert acq.loc["4", "qty_base"] == pytest.approx(10 * 12 * 12)
    assert acq.loc["3", "price_exclusion"] == "unit_unconverted"
    hit = p.data_quality.query("rule == 'unit_unconverted' and company == 'acquirer'").iloc[0]
    assert (hit["severity"], hit["rows"]) == ("info", 1)


def test_meta_contents(run):
    p = run([{}], period_end="2024-03")
    assert set(p.meta) >= {
        "period",
        "scaling_factor",
        "reporting_currency",
        "in_scope_spend",
        "addressable_spend",
        "not_item_addressable",
        "features",
    }
    assert p.meta["reporting_currency"] == "USD"
    assert p.meta["rows"] == {"acquirer": 1, "target": 1}


def test_prepare_60000_lines_is_fast():
    rng = np.random.default_rng(7)
    taxonomy = load_taxonomy()
    n = 30_000
    native = ["Fasteners", "Freight", "Bearings", "Oil", "Misc"]
    desc = [f"ITEM {i % 500} BOX OF {2 + i % 40}" for i in range(500)]

    def frame(company: str) -> pd.DataFrame:
        month = rng.integers(0, 12, n)
        qty = rng.integers(1, 100, n)
        price = rng.integers(1, 500, n) / 10
        item = rng.integers(0, 500, n)
        df = pd.DataFrame(
            {
                "site": "P1",
                "doc_date": [f"{2023 + (m + 3) // 12}-{(m + 3) % 12 + 1:02d}-15" for m in month],
                "vendor_id": [f"V{v}" for v in rng.integers(0, 2000, n)],
                "vendor_name": [f"Vendor {v}" for v in rng.integers(0, 2000, n)],
                "item_code": [f"I{i}" for i in item],
                "item_description": [desc[i] for i in item],
                "category_native": rng.choice(native, n),
                "uom": rng.choice(["EA", "BX", "KG", "M", "PR"], n),
                "quantity": qty.astype(str),
                "unit_price": price.astype(str),
                "line_amount": (qty * price).astype(str),
                "currency": rng.choice(["USD", "CAD", "EUR"], n),
            }
        ).astype(object)
        df["company"] = company
        df["source_file"] = "f.csv"
        df["source_row"] = np.arange(n) + 2
        df["line_id"] = company + ":" + df["source_row"].astype(str)
        return df

    cmap = pd.DataFrame(
        {
            "company": ["acquirer"] * 5 + ["target"] * 5,
            "category_native": native * 2,
            "l2_code": ["L02.01", "L11.01", "L03.01", "L09.01", "L10.01"] * 2,
        }
    )
    started = time.perf_counter()
    p = prepare(frame("acquirer"), frame("target"), fx=FX, taxonomy=taxonomy, category_map=cmap)
    elapsed = time.perf_counter() - started
    assert len(p.lines) == 2 * n
    assert elapsed < 15, f"prepare took {elapsed:.1f}s"
