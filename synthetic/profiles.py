"""Named generator profiles: small, documented overrides of ``GeneratorConfig``.

A profile changes the *story* a dataset tells (deal size, data quality,
overlap) without touching the generator's code. ``default`` is the documented
configuration and the only one the accuracy scorecard's held-out seed (4) uses;
the others exist for the extra sample mergers and are never used for tuning.

``python -m synthetic --seed N --out DIR --profile NAME`` applies one.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from synthetic.config import DEFAULT_CONFIG, CompanyShape, GeneratorConfig

#: Profile name -> (one-line description, GeneratorConfig field overrides).
PROFILES: dict[str, tuple[str, dict[str, Any]]] = {
    "default": ("The documented defaults (the held-out demo seed).", {}),
    "bolt_on": (
        "A large acquirer buys a much smaller target: the target is a quarter of its "
        "default size, so only a small slice of the combined spend can be harmonised.",
        {
            "target": CompanyShape(45e6, 5_500, 250, 900, 3),
            "shared_item_share": 0.12,
            "near_identical_pairs": 100,
            "unit_trap_count": 40,
            "freight_gap_items": 15,
            "similar_vendor_pairs": 25,
        },
    ),
    "messy": (
        "Poor master data: more vendor typos and aliases, more missing tax ids and "
        "manufacturers, more unit-of-measure traps, so the naive figure is more inflated.",
        {
            "typo_rate": 0.16,
            "alias_rate_shared": 0.60,
            "tax_id_missing_rate": 0.55,
            "manufacturer_blank_rate": 0.22,
            "unit_trap_count": 300,
            "memorable_trap_spend_usd": 3e6,
            "spot_buy_rate": 0.08,
            "near_identical_pairs": 700,
        },
    ),
    "high_overlap": (
        "Two businesses in the same niche: more shared suppliers and more items both "
        "companies buy, so more of the combined spend can be harmonised.",
        {
            "shared_parent_rate": 0.45,
            "shared_item_share": 0.55,
            "same_vendor_bias": 0.85,
            "shared_spend_lift": 2.0,
        },
    ),
}


def profile_config(name: str, base: GeneratorConfig = DEFAULT_CONFIG) -> GeneratorConfig:
    """``base`` with the named profile's overrides applied."""
    if name not in PROFILES:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"unknown profile {name!r}; known profiles: {known}")
    return replace(base, **PROFILES[name][1])
