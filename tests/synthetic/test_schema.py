import pandas as pd

from synthetic.config import COMPANIES

PRD_COLUMNS = [
    "site",
    "doc_date",
    "vendor_id",
    "vendor_name",
    "vendor_tax_id",
    "vendor_country",
    "item_code",
    "item_description",
    "mpn",
    "manufacturer",
    "category_native",
    "uom",
    "pack_qty",
    "quantity",
    "unit_price",
    "line_amount",
    "currency",
    "payment_terms_days",
    "payment_date",
    "contract_id",
    "contract_end_date",
    "incoterm",
    "spend_type",
    "po_number",
    "po_line",
]
REQUIRED = [
    "site",
    "doc_date",
    "vendor_id",
    "vendor_name",
    "item_description",
    "category_native",
    "quantity",
    "unit_price",
    "line_amount",
    "currency",
]


def test_purchase_line_columns_match_prd(small):
    for company in COMPANIES:
        assert list(small.purchase_lines(company).columns) == PRD_COLUMNS


def test_required_fields_present_and_valid(small):
    for company in COMPANIES:
        df = small.purchase_lines(company)
        for col in REQUIRED:
            assert df[col].notna().all() and (df[col].astype(str) != "").all(), col
        dates = pd.to_datetime(df["doc_date"])
        assert dates.min() >= pd.Timestamp("2025-01-01") and dates.max() <= pd.Timestamp(
            "2025-12-31"
        )
        assert df["vendor_country"].str.fullmatch(r"[A-Z]{2}").all()
        assert set(df["currency"]) <= {"USD", "CAD", "EUR"}
        assert set(df["spend_type"]) <= {"direct", "indirect"}
        coded = (df["item_code"] != "") | (df["mpn"] != "")
        assert (df.loc[coded, "uom"] != "").all()


def test_line_amount_equals_quantity_times_price(small):
    for company in COMPANIES:
        df = small.purchase_lines(company)
        qty = df["quantity"].astype(float)
        diff = (df["line_amount"] - qty * df["unit_price"]).abs()
        assert (diff <= (0.01 * df["line_amount"].abs()).clip(lower=0.01)).all()
        assert (df.loc[qty > 0, "unit_price"] > 0).all()


def test_reference_and_truth_columns(small):
    assert list(small.vendor_parents.columns) == ["key_type", "key", "country", "parent_name"]
    assert set(small.vendor_parents["key_type"]) <= {"name", "tax_id"}
    assert list(small.category_map.columns) == ["company", "category_native", "l2_code"]
    assert list(small.truth_vendor_map.columns) == [
        "company",
        "vendor_id",
        "true_legal_entity",
        "true_parent",
    ]
    assert list(small.truth_item_map.columns[:3]) == ["company", "item_key", "true_item_id"]
    assert list(small.truth_savings.columns[:5]) == [
        "true_item_id",
        "cause",
        "true_gross_gap_usd",
        "is_unit_trap",
        "is_distractor",
    ]


def test_category_map_covers_mapped_natives(small):
    mapped = set(
        zip(small.category_map["company"], small.category_map["category_native"], strict=True)
    )
    for company in COMPANIES:
        natives = set(small.purchase_lines(company)["category_native"])
        unmapped = {n for n in natives if (company, n) not in mapped}
        assert len(unmapped) == 1  # the deliberate "miscellaneous" bucket
