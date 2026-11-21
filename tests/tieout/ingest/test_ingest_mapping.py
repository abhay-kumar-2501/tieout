from tieout.ingest.mapping import missing_required, suggest_mapping, to_mapping


def by_header(headers):
    return {s.header: s for s in suggest_mapping(headers)}


def test_exact_synonym_match():
    s = by_header(["Supplier Name", "PO Date", "MATNR", "Net Price"])
    assert (s["Supplier Name"].field, s["Supplier Name"].method) == ("vendor_name", "exact")
    assert s["PO Date"].field == "doc_date"
    assert s["MATNR"].field == "item_code"
    assert s["Net Price"].field == "unit_price"
    assert s["Net Price"].score == 100.0


def test_schema_name_is_an_exact_match_after_normalisation():
    s = by_header(["vendor_tax_id", "Contract-End-Date"])
    assert s["vendor_tax_id"].method == "exact"
    assert s["Contract-End-Date"].field == "contract_end_date"


def test_fuzzy_match_at_threshold_and_below():
    s = by_header(["Vendr Name", "Qty Orderd", "Zzzz Column"])
    assert (s["Vendr Name"].field, s["Vendr Name"].method) == ("vendor_name", "fuzzy")
    assert s["Vendr Name"].score >= 80
    assert s["Zzzz Column"].field is None
    assert s["Zzzz Column"].method == "none"


def test_fuzzy_ignores_word_order():
    assert by_header(["Description Item"])["Description Item"].field == "item_description"


def test_a_field_is_suggested_once():
    out = suggest_mapping(["Supplier Name", "Vendor Name"])
    assert [s.field for s in out] == ["vendor_name", None]


def test_suggestions_keep_header_order_and_to_mapping():
    out = suggest_mapping(["B", "Plant", "A"])
    assert [s.header for s in out] == ["B", "Plant", "A"]
    assert to_mapping(out) == {"Plant": "site"}


def test_missing_required():
    assert "doc_date" in missing_required(["site"])
    assert "doc_date" not in missing_required(["site"], aggregated=True)
    assert "uom" in missing_required(["site"])
    assert "uom" not in missing_required(["site"], has_items=False)
    everything = [
        "site",
        "doc_date",
        "vendor_id",
        "vendor_name",
        "item_description",
        "category_native",
        "uom",
        "quantity",
        "unit_price",
        "line_amount",
        "currency",
    ]
    assert missing_required(everything) == []
