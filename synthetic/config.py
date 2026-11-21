"""Every rate, count and scale constant the generator uses (PRD 8.1-8.3).

All values live in one frozen dataclass so a later calibration step can
adjust them in one place. Counts are full-size figures; ``scale`` multiplies
every count and every spend figure, which keeps small test datasets
proportionate.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

COMPANIES: tuple[str, str] = ("acquirer", "target")


@dataclass(frozen=True)
class CompanyShape:
    """Size of one company's purchasing data at scale 1."""

    spend_usd: float
    lines: int
    vendor_records: int
    item_records: int
    sites: int


@dataclass(frozen=True)
class GeneratorConfig:
    """Documented defaults of the demo-data generator."""

    scale: float = 1.0

    # --- 8.1 shape -------------------------------------------------------
    acquirer: CompanyShape = CompanyShape(340e6, 38_000, 1_500, 5_500, 8)
    target: CompanyShape = CompanyShape(180e6, 22_000, 1_000, 3_500, 5)
    period_start: date = date(2025, 1, 1)
    period_end: date = date(2025, 12, 31)
    close_date: date = date(2026, 1, 1)

    # Spend with neither item code nor MPN (PRD 8.3 target: about 35%).
    service_spend_share: float = 0.24  # L11 and L12, never item-coded
    free_text_spend_share: float = 0.11  # goods bought on free text
    service_line_share: float = 0.16
    free_text_line_share: float = 0.09
    unmapped_native_spend_share: float = 0.01  # free text in a native "misc" bucket

    # --- 8.2 vendors -------------------------------------------------------
    shared_parent_rate: float = 0.25
    alias_rate_shared: float = 0.40  # alias or legal-form variant on shared vendors
    typo_rate: float = 0.08
    target_name_length: int = 30
    acquirer_name_length: int = 40
    tax_id_missing_rate: float = 0.30
    no_similarity_parent_rate: float = 0.05
    multi_entity_parent_rate: float = 0.12  # parents with sibling legal entities
    cross_entity_shared_rate: float = 0.15  # shared parents reached via different entities
    duplicate_vendor_record_rate: float = 0.03  # second vendor id for one entity
    distributor_rate: float = 0.08
    country_shares: tuple[tuple[str, float], ...] = (
        ("US", 0.74),
        ("CA", 0.17),
        ("DE", 0.04),
        ("FR", 0.02),
        ("NL", 0.015),
        ("IT", 0.015),
    )

    # --- 8.2 items ---------------------------------------------------------
    shared_item_share: float = 0.35  # of all item records (both companies)
    mpn_both_sides_rate: float = 0.60  # shared items with MPN on both records
    mpn_one_side_rate: float = 0.25
    mpn_rate_unshared: float = 0.45
    mpn_only_record_rate: dict[str, float] = field(
        default_factory=lambda: {"acquirer": 0.03, "target": 0.07}
    )
    manufacturer_blank_rate: float = 0.12
    manufacturer_abbreviated_rate: float = 0.10
    pack_difference_rate: float = 0.12  # of shared items
    pack_info_split: tuple[float, float, float] = (0.50, 0.25, 0.25)  # text, column, none
    unshared_pack_rate: float = 0.35  # unshared items sold in packs that are bought by the pack
    acquirer_description_length: int = 50
    target_description_length: int = 40

    # --- 8.2 commercial ----------------------------------------------------
    contract_spend_share: float = 0.40
    contract_end_months: tuple[int, int] = (-6, 48)  # relative to close_date
    payment_date_rate: float = 0.90
    incoterm_rate: float = 0.70
    standard_incoterm: str = "FCA"  # both companies' procurement default
    standard_incoterm_rate: float = 0.90
    currency_shares: tuple[tuple[str, float], ...] = (
        ("USD", 0.85),
        ("CAD", 0.10),
        ("EUR", 0.05),
    )
    # Mirrors the shipped illustrative table: amount x rate = USD.
    fx_to_usd: tuple[tuple[str, float], ...] = (("USD", 1.00), ("CAD", 0.73), ("EUR", 1.08))
    return_line_rate: float = 0.01
    payment_terms_choices: dict[str, tuple[tuple[int, float], ...]] = field(
        default_factory=lambda: {
            "acquirer": ((30, 0.15), (45, 0.20), (60, 0.40), (75, 0.10), (90, 0.15)),
            "target": ((15, 0.05), (30, 0.50), (45, 0.30), (60, 0.15)),
        }
    )

    # --- 8.2 distractors ---------------------------------------------------
    near_identical_pairs: int = 300
    near_identical_shared_share: float = 0.33  # sibling sits next to a truly shared item
    similar_vendor_pairs: int = 60
    freight_gap_items: int = 40
    freight_premium: tuple[float, float] = (0.06, 0.14)
    spot_buy_rate: float = 0.03
    spot_discount: tuple[float, float] = (0.28, 0.45)

    # --- 8.3 calibration knobs ---------------------------------------------
    unit_trap_count: int = 70
    unit_trap_as_each_share: float = 0.60  # rest are pack units with no size anywhere
    memorable_trap_spend_usd: float = 1.2e6
    memorable_trap_factor: int = 12
    price_gap_scale: float = 1.0
    gap_item_rate: float = 0.75  # shared items with a planted price gap
    gap_median: float = 0.22  # median relative gap before scaling
    shared_spend_lift: float = 1.6  # log-scale spend boost of items both companies buy
    gap_sigma: float = 0.55
    same_vendor_bias: float = 0.65  # shared items routed to shared parents
    same_parent_given_shared: float = 0.80
    site_price_dispersion: float = 0.012
    line_price_dispersion: float = 0.004
    second_vendor_rate: float = 0.18  # unshared items bought from two vendors
    second_vendor_premium: tuple[float, float] = (0.03, 0.15)
    concentration_l2: str = "L03.01"
    concentration_share: float = 0.53
    memorable_trap_l2: str = "L06.03"

    # --- output -----------------------------------------------------------
    report_date: date = date(2026, 1, 15)

    def company(self, name: str) -> CompanyShape:
        return self.acquirer if name == "acquirer" else self.target

    def count(self, full_size: int, minimum: int = 1) -> int:
        """A full-size count scaled to this configuration."""
        return max(minimum, int(round(full_size * self.scale)))

    def fx(self) -> dict[str, float]:
        return dict(self.fx_to_usd)

    def scaled(self, scale: float) -> GeneratorConfig:
        return replace(self, scale=scale)


DEFAULT_CONFIG = GeneratorConfig()
