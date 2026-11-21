"""Calibration summary (PRD 8.3), computed from the generator's own truth.

The synergy engine cannot be run here, so two proxies stand in for it: the
naive figure with perfect item matching (every buying group against the
item's cheapest group, packs and traps compared at recorded prices, gaps
inside one company counted), and lever 1 with perfect matching and the base
capture probabilities. The engine's figures will be lower than the proxies
wherever it misses a match.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from synthetic.config import COMPANIES
from synthetic.generate import Dataset

PI_BASE = {"price_gap_same_vendor": 0.70, "price_gap_switch": 0.40}
HORIZON_MONTHS = 36


def _horizon(close: date) -> str:
    y, m = divmod(close.month - 1 + HORIZON_MONTHS, 12)
    return date(close.year + y, m + 1, close.day).isoformat()


def naive_proxy(ds: Dataset) -> float:
    parts = []
    for c in COMPANIES:
        df = ds.lines[c]
        df = df[df["_item"] != ""].assign(company=c)
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["_seen_qty"] = df["quantity"] * df["_seen_factor"]
    g = df.groupby(["_item", "company", "site", "_parent"], sort=True)[["_usd", "_seen_qty"]].sum()
    g = g[g["_seen_qty"] > 0]
    g["price"] = g["_usd"] / g["_seen_qty"]
    low = g.groupby(level="_item")["price"].transform("min")
    return float(((g["price"] - low) * g["_seen_qty"]).sum())


def lever1_proxy(ds: Dataset) -> float:
    sav = ds.truth_savings
    by_id = {s.item.item_id: s for s in ds.world.shared}
    horizon = _horizon(ds.config.close_date)
    total = 0.0
    for row in sav.itertuples(index=False):
        pi = PI_BASE.get(row.cause)
        s = by_id.get(row.true_item_id)
        if pi is None or s is None:
            continue
        if any(h.pack_size and h.pack_mode == "none" for h in (s.acquirer, s.target)):
            continue
        df = ds.lines[row.higher_company]
        df = df[(df["_item"] == row.true_item_id) & (df["_kind"] != "spot")]
        end = df["contract_end_date"]
        free = df.loc[(end == "") | (end <= horizon), "_base_qty"].sum()
        qty = df["_base_qty"].sum()
        share = float(free / qty) if qty > 0 else 0.0
        total += row.true_gross_gap_usd * share * pi
    return total


def summarise(ds: Dataset) -> dict[str, object]:
    cfg, world = ds.config, ds.world
    out: dict[str, object] = {"seed": ds.seed, "scale": cfg.scale}
    total = 0.0
    for c in COMPANIES:
        df = ds.lines[c]
        spend = float(df["_usd"].sum())
        total += spend
        no_item = df[(df["item_code"] == "") & (df["mpn"] == "")]["_usd"].sum()
        out[c] = {
            "in_scope_spend_usd": round(spend),
            "lines": len(df),
            "vendor_records": len(ds.vendors[c]),
            "item_records": len(ds.items[c]),
            "sites": int(df["site"].nunique()),
            "spend_without_item_code_or_mpn": round(float(no_item) / spend, 4),
        }
    out["combined_spend_usd"] = round(total)
    shared_entities = {v.record.entity.entity_id for v in ds.vendors["acquirer"]} & {
        v.record.entity.entity_id for v in ds.vendors["target"]
    }
    sav = ds.truth_savings
    shared = sav[sav["true_item_id"].isin([s.item.item_id for s in world.shared])]
    gross = float(shared["true_gross_gap_usd"].sum())
    out["shared_parents"] = sum(1 for p in world.parents if p.shared)
    out["parents"] = len(world.parents)
    out["shared_legal_entities"] = len(shared_entities)
    out["shared_items"] = len(world.shared)
    out["shared_items_same_vendor"] = int((shared["cause"] == "price_gap_same_vendor").sum())
    out["shared_items_switch"] = int((shared["cause"] == "price_gap_switch").sum())
    out["planted_gross_gap_usd"] = round(gross)
    out["planted_gross_gap_pct_of_spend"] = round(100 * gross / total, 2)
    naive = naive_proxy(ds)
    lever1 = lever1_proxy(ds)
    out["naive_proxy_pct_of_spend"] = round(100 * naive / total, 2)
    out["lever1_base_proxy_pct_of_spend"] = round(100 * lever1 / total, 2)
    d = ds.truth_distractors
    packs = [h for s in world.shared for h in (s.acquirer, s.target) if h.pack_size and not h.trap]
    out["distractors"] = {
        "near_identical_item_pairs": int((d["type"] == "near_identical").sum()),
        "similar_vendor_pairs": len(world.similar_vendor_pairs),
        "freight_term_gaps": int((d["type"] == "freight_terms").sum()),
        "unit_traps": int((d["type"] == "unit_trap").sum()),
        "spot_buys": int((d["type"] == "spot_buy").sum()),
        "pack_differences": len(packs),
        "pack_differences_by_mode": {
            m: sum(1 for h in packs if h.pack_mode == m) for m in ("text", "column", "none")
        },
    }
    star = next((s for s in world.shared if s.item.item_id == world.memorable_trap), None)
    if star is not None:
        out["memorable_unit_trap"] = {
            "true_item_id": star.item.item_id,
            "l2": star.item.category.l2,
            "target_spend_usd": round(star.target.spend),
            "pack_factor": star.target.pack_size,
        }
    l2 = cfg.concentration_l2
    held = combined = 0.0
    for c in COMPANIES:
        df = ds.lines[c]
        df = df[df["_l2"] == l2]
        combined += float(df["_usd"].sum())
        held += float(df.loc[df["_parent"] == world.concentration_parent, "_usd"].sum())
    out["concentration"] = {
        "l2": l2,
        "parent": world.concentration_parent,
        "parent_share_of_l2_spend": round(held / combined, 3) if combined else 0.0,
    }
    return out


def format_summary(summary: dict[str, object], indent: int = 0) -> str:
    lines = []
    pad = "  " * indent
    for key, value in summary.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(format_summary(value, indent + 1))
        elif isinstance(value, int) and abs(value) >= 10_000:
            lines.append(f"{pad}{key}: {value:,}")
        else:
            lines.append(f"{pad}{key}: {value}")
    return "\n".join(lines)
