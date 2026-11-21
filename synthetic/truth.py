"""Truth files (PRD 4.7), computed from the generated lines themselves.

``truth_savings.csv`` defines ``true_gross_gap_usd`` exactly as lever 1's
gross gap would be with perfect matching, a single buying group per company,
no contract filter and no capture probability: the difference between the two
companies' volume-weighted USD prices per base unit (spot buys excluded,
returns netted), times the dearer company's annual base-unit quantity. Gaps
explained by freight terms, and items that only look alike, are zero.
"""

from __future__ import annotations

import re

import pandas as pd

from synthetic.config import COMPANIES
from synthetic.model import World
from synthetic.names import normalise_name
from synthetic.render import ItemView, VendorView

SAVINGS_COLUMNS = ["true_item_id", "cause", "true_gross_gap_usd", "is_unit_trap", "is_distractor"]
ZERO_GAP_CAUSES = ("freight_terms", "near_identical")


def item_key(item_code: str, mpn: str, manufacturer: str) -> str:
    """ARCHITECTURE.md item key: the code, else ``MPN:{mpn_norm}|{manufacturer_norm}``."""
    if item_code:
        return item_code
    mpn_norm = re.sub(r"[^0-9A-Z]", "", mpn.upper())
    return f"MPN:{mpn_norm}|{normalise_name(manufacturer) if manufacturer else ''}"


def vendor_map(vendors: dict[str, list[VendorView]]) -> pd.DataFrame:
    rows = [
        {
            "company": c,
            "vendor_id": v.vendor_id,
            "true_legal_entity": v.record.entity.entity_id,
            "true_parent": v.record.parent.parent_id,
        }
        for c in COMPANIES
        for v in vendors[c]
    ]
    return pd.DataFrame(rows).sort_values(
        ["company", "vendor_id"], kind="mergesort", ignore_index=True
    )


def item_map(items: dict[str, list[ItemView]]) -> pd.DataFrame:
    rows = [
        {
            "company": c,
            "item_key": item_key(v.item_code, v.mpn, v.manufacturer),
            "true_item_id": v.holding.item.item_id,
            "item_code": v.item_code,
            "mpn": v.mpn,
            "manufacturer": v.manufacturer,
        }
        for c in COMPANIES
        for v in items[c]
    ]
    return pd.DataFrame(rows).sort_values(
        ["company", "item_key"], kind="mergesort", ignore_index=True
    )


def company_prices(lines: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Volume-weighted USD price per base unit and net base quantity per company and item."""
    parts = []
    for c in COMPANIES:
        df = lines[c]
        df = df[df["_kind"].isin(["item", "return"]) & (df["_item"] != "")]
        g = df.groupby("_item", sort=True)[["_usd", "_base_qty"]].sum()
        g["company"] = c
        parts.append(g.reset_index())
    out = pd.concat(parts, ignore_index=True)
    out["price"] = out["_usd"] / out["_base_qty"]
    return out


def savings(world: World, lines: dict[str, pd.DataFrame]) -> pd.DataFrame:
    table = company_prices(lines)
    prices = {
        (c, i): {"company": c, "price": p, "_base_qty": q}
        for c, i, p, q in zip(
            table["company"], table["_item"], table["price"], table["_base_qty"], strict=True
        )
    }
    spot_items = {
        (c, i)
        for c in COMPANIES
        for i in lines[c].loc[lines[c]["_kind"] == "spot", "_item"].tolist()
    }
    rows = []
    for s in world.shared:
        iid = s.item.item_id
        pa = prices[("acquirer", iid)]
        pt = prices[("target", iid)]
        hi, lo = (pa, pt) if pa["price"] >= pt["price"] else (pt, pa)
        gap = max(0.0, float(hi["price"] - lo["price"])) * max(0.0, float(hi["_base_qty"]))
        if s.cause in ZERO_GAP_CAUSES:
            gap = 0.0
        kinds = [s.distractor] if s.distractor else []
        if ("acquirer", iid) in spot_items or ("target", iid) in spot_items:
            kinds.append("spot_buy")
        rows.append(
            {
                "true_item_id": iid,
                "cause": s.cause,
                "true_gross_gap_usd": round(gap, 2),
                "is_unit_trap": int(s.distractor == "unit_trap"),
                "is_distractor": int(bool(kinds)),
                "distractor_type": "+".join(kinds),
                "planted_gap": round(s.gap, 6),
                "higher_company": str(hi["company"]),
                "acquirer_price_usd": round(float(pa["price"]), 6),
                "target_price_usd": round(float(pt["price"]), 6),
                "higher_qty_base": round(float(hi["_base_qty"]), 3),
            }
        )
    shared_ids = {s.item.item_id for s in world.shared}
    for anchor, sib in world.near_identical:
        for item in (anchor, sib):
            if item.item_id in shared_ids:
                continue
            rows.append(
                {
                    "true_item_id": item.item_id,
                    "cause": "near_identical",
                    "true_gross_gap_usd": 0.0,
                    "is_unit_trap": 0,
                    "is_distractor": 1,
                    "distractor_type": "near_identical",
                    "planted_gap": 0.0,
                    "higher_company": "",
                    "acquirer_price_usd": None,
                    "target_price_usd": None,
                    "higher_qty_base": None,
                }
            )
            shared_ids.add(item.item_id)
    return pd.DataFrame(rows).sort_values("true_item_id", kind="mergesort", ignore_index=True)


def distractors(
    world: World, vendors: dict[str, list[VendorView]], items: dict[str, list[ItemView]]
) -> pd.DataFrame:
    """Every planted distractor with the record keys a careless matcher would confuse."""
    vid = {c: {} for c in COMPANIES}
    for c in COMPANIES:
        for v in vendors[c]:
            vid[c].setdefault(v.record.parent.parent_id, []).append(v.vendor_id)
    ikey = {
        c: {v.holding.item.item_id: item_key(v.item_code, v.mpn, v.manufacturer) for v in items[c]}
        for c in COMPANIES
    }
    rows = []
    for a, b, kind in world.similar_vendor_pairs:
        for va in vid["acquirer"].get(a.parent_id, []):
            for vb in vid["target"].get(b.parent_id, []):
                rows.append(("similar_vendor", kind, "acquirer", va, "target", vb))
    for anchor, sib in world.near_identical:
        rows.append(
            (
                "near_identical",
                "",
                "acquirer",
                ikey["acquirer"][anchor.item_id],
                "target",
                ikey["target"][sib.item_id],
            )
        )
    for s in world.shared:
        if s.distractor in ("unit_trap", "freight_terms"):
            iid = s.item.item_id
            trap = next((h.company for h in (s.acquirer, s.target) if h.trap), "")
            note = (
                f"{trap}:{'+'.join(h.trap for h in (s.acquirer, s.target) if h.trap)}"
                if trap
                else ""
            )
            rows.append(
                (
                    s.distractor,
                    note,
                    "acquirer",
                    ikey["acquirer"][iid],
                    "target",
                    ikey["target"][iid],
                )
            )
    for c in COMPANIES:
        for v in items[c]:
            if v.holding.spot:
                rows.append(("spot_buy", "", c, ikey[c][v.holding.item.item_id], "", ""))
    df = pd.DataFrame(rows, columns=["type", "detail", "company_a", "key_a", "company_b", "key_b"])
    return df.sort_values(
        ["type", "company_a", "key_a", "key_b"], kind="mergesort", ignore_index=True
    )
