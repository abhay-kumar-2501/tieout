"""The PRD 3.1 input schema: column names, types and limits."""

from __future__ import annotations

from typing import Final

COMPANIES: Final = ("acquirer", "target")

MAX_ROWS: Final = 250_000
MAX_BYTES: Final = 50 * 1024 * 1024

#: Every PRD 3.1 column, in the order the ``lines`` frame carries them.
COLUMNS: Final[tuple[str, ...]] = (
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
)

DATE_COLUMNS: Final = ("doc_date", "payment_date", "contract_end_date")
NUMBER_COLUMNS: Final = ("pack_qty", "quantity", "unit_price", "line_amount", "payment_terms_days")
TEXT_COLUMNS: Final = tuple(c for c in COLUMNS if c not in DATE_COLUMNS + NUMBER_COLUMNS)

#: Always required. ``doc_date`` is dropped in aggregated mode; ``uom`` is
#: required only when some row carries an item code or MPN.
REQUIRED: Final = (
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
)

#: Columns added at load.
LOAD_COLUMNS: Final = ("company", "source_file", "source_row", "line_id")


def required_columns(aggregated: bool) -> tuple[str, ...]:
    """The unconditionally required columns for the given mode."""
    return tuple(c for c in REQUIRED if not (aggregated and c == "doc_date"))
