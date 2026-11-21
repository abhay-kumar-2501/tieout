"""Purchase lines (PRD 3.1) for each company, with commercial noise.

Lines are built in US dollars against the true world, then currencies,
payment terms, incoterms, contracts and PO numbers are layered on. Hidden
columns (prefixed ``_``) carry what truth needs and are dropped on output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from synthetic.config import COMPANIES, GeneratorConfig
from synthetic.model import Category, Holding, VendorRecord, World
from synthetic.render import (
    MISC_NATIVE,
    ItemView,
    Style,
    VendorView,
    free_text_description,
)

OUTPUT_COLUMNS = [
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
SITES = {
    "acquirer": (
        "A100 Dayton OH",
        "A200 Toledo OH",
        "A300 Fort Wayne IN",
        "A400 Peoria IL",
        "A500 Wichita KS",
        "A600 Tulsa OK",
        "A700 Greenville SC",
        "A800 Monterrey MX",
    ),
    "target": (
        "T10 Hamilton ON",
        "T20 Windsor ON",
        "T30 Erie PA",
        "T40 Racine WI",
        "T50 Saginaw MI",
    ),
}
INTEGER_UNITS = {"EA", "PC", "PR", "BX", "CS", "PK", "FT", "LB"}
DIRECT_L1 = {"L01", "L02", "L03", "L04"}
SERVICE_TEXT = {
    "L11.01": (
        "LTL FREIGHT {a}-{b} PRO {n}",
        "TRUCKLOAD {a} TO {b} LOAD {n}",
        "FUEL SURCHARGE PRO {n}",
    ),
    "L11.02": ("PARCEL CHARGES WEEK {w}", "EXPRESS SHIPMENT AWB {n}", "COURIER SERVICE INV {n}"),
    "L11.03": ("OCEAN FREIGHT 40FT {a}-{b} BL {n}", "AIR FREIGHT AWB {n}", "LCL CONSOLIDATION {n}"),
    "L11.04": ("WAREHOUSING STORAGE {m}", "3PL HANDLING FEES {m}", "PICK PACK CHARGES {m}"),
    "L11.05": ("CUSTOMS ENTRY {n}", "BROKERAGE FEE ENTRY {n}", "DUTY AND TAXES ENTRY {n}"),
    "L12.01": ("SOFTWARE SUBSCRIPTION {m}", "CLOUD HOSTING {m}", "ERP LICENSE MAINTENANCE {m}"),
    "L12.02": ("LAPTOP 14IN 16GB", "NETWORK SWITCH 48 PORT", "MOBILE SERVICE {m}", "MONITOR 27IN"),
    "L12.03": ("TEMP LABOR WE {d}", "CONTRACT WELDER WE {d}", "AGENCY STAFF WE {d}"),
    "L12.04": ("ENGINEERING SERVICES PROJ {n}", "CONSULTING FEES {m}", "SAFETY TRAINING {m}"),
    "L12.05": ("LEGAL SERVICES {m}", "AUDIT FEES {m}", "INSURANCE PREMIUM {m}"),
}
HOURLY_L2 = {"L12.03", "L12.04"}
CITIES = (
    "DAYTON",
    "TOLEDO",
    "CHICAGO",
    "DETROIT",
    "HAMILTON",
    "ERIE",
    "TULSA",
    "LAREDO",
    "MEMPHIS",
)
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


@dataclass
class _Builder:
    cfg: GeneratorConfig
    rng: np.random.Generator
    company: str
    style: Style
    vendor_view: dict[int, VendorView]

    def __post_init__(self) -> None:
        self.rows: list[dict] = []
        days = (self.cfg.period_end - self.cfg.period_start).days + 1
        self.days = [self.cfg.period_start + timedelta(d) for d in range(days)]
        self.workdays = [d for d in self.days if d.weekday() < 5]
        sites = SITES[self.company]
        self.sites = sites
        w = np.array([1.0 / (1 + 0.35 * i) for i in range(len(sites))])
        self.site_p = w / w.sum()

    def date(self) -> date:
        return self.workdays[int(self.rng.integers(len(self.workdays)))]

    def site(self) -> str:
        return self.sites[int(self.rng.choice(len(self.sites), p=self.site_p))]

    def add(
        self,
        *,
        vendor: VendorRecord,
        cat: Category,
        description: str,
        native: str,
        qty: float,
        usd_price: float,
        kind: str,
        uom: str = "",
        item: ItemView | None = None,
        base_per_unit: float = 1.0,
        site: str | None = None,
        day: date | None = None,
    ) -> None:
        h = item.holding if item else None
        self.rows.append(
            {
                "site": site or self.site(),
                "doc_date": day or self.date(),
                "_vendor": vendor,
                "item_code": item.item_code if item else "",
                "item_description": description,
                "mpn": item.mpn if item else "",
                "manufacturer": item.manufacturer if item else "",
                "category_native": native,
                "uom": uom,
                "pack_qty": item.pack_qty if item else None,
                "quantity": qty,
                "_usd_price": usd_price,
                "spend_type": "direct" if cat.l1 in DIRECT_L1 else "indirect",
                "_kind": kind,
                "_l2": cat.l2,
                "_item": h.item.item_id if h else "",
                "_parent": vendor.parent.parent_id,
                "_base_per_unit": base_per_unit,
                # What a careful engine can see: unconverted packs and traps look like each.
                "_seen_factor": 1.0
                if h and (h.trap or (h.pack_size and h.pack_mode == "none"))
                else base_per_unit,
                "_incoterm": h.incoterm if h else "",
            }
        )


def _round_qty(q: float, uom: str) -> float:
    return float(max(1, round(q))) if uom in INTEGER_UNITS else max(0.1, round(q, 1))


def _item_lines(
    b: _Builder, views: list[ItemView], budget: int, pools: dict[str, list[VendorRecord]]
) -> None:
    cfg, rng = b.cfg, b.rng
    spends = np.array([v.holding.spend for v in views])
    raw = np.power(np.maximum(spends, 1.0), 0.45)
    scale = budget / raw.sum()
    for view, r in zip(views, raw, strict=True):
        h = view.holding
        cat = h.item.category
        assert h.vendor is not None
        p_rec = h.price * view.base_per_unit
        q_rec = h.spend / p_rec
        n = max(1, int(round(r * scale)))
        if view.uom in INTEGER_UNITS:
            n = max(1, min(n, int(q_rec)))
        n = min(n, 80)
        k = int(min(n, 1 + rng.poisson(0.9), len(b.sites)))
        sites = [
            b.sites[int(i)] for i in rng.choice(len(b.sites), size=k, replace=False, p=b.site_p)
        ]
        site_mult = {s: math.exp(rng.normal(0.0, cfg.site_price_dispersion)) for s in sites}
        shares = rng.dirichlet(np.full(n, 2.0))
        n_second = int(round(n * h.second_share)) if h.second_vendor else 0
        for j in range(n):
            vendor, price = h.vendor, p_rec
            if j < n_second and h.second_vendor is not None:
                vendor, price = h.second_vendor, p_rec * (1.0 + h.second_premium)
            site = sites[j % k]
            unit_price = (
                price * site_mult[site] * math.exp(rng.normal(0.0, cfg.line_price_dispersion))
            )
            b.add(
                vendor=vendor,
                cat=cat,
                description=view.description,
                native=view.category_native,
                qty=_round_qty(q_rec * shares[j], view.uom),
                usd_price=unit_price,
                kind="item",
                uom=view.uom,
                item=view,
                base_per_unit=view.base_per_unit,
                site=site,
            )
        if h.spot:
            others = [v for v in pools[cat.l2] if v.parent is not h.vendor.parent]
            if others:
                vendor = others[int(rng.integers(len(others)))]
                qty = _round_qty(q_rec * rng.uniform(0.02, 0.05), view.uom)
                price = p_rec * (1.0 - rng.uniform(*cfg.spot_discount))
                b.add(
                    vendor=vendor,
                    cat=cat,
                    description=view.description,
                    native=view.category_native,
                    qty=qty,
                    usd_price=price,
                    kind="spot",
                    uom=view.uom,
                    item=view,
                    base_per_unit=view.base_per_unit,
                    site=sites[0],
                )


def _service_text(l2: str, rng: np.random.Generator) -> str:
    template = SERVICE_TEXT[l2][int(rng.integers(len(SERVICE_TEXT[l2])))]
    a, b = (CITIES[int(i)] for i in rng.choice(len(CITIES), size=2, replace=False))
    return template.format(
        a=a,
        b=b,
        n=int(rng.integers(100000, 999999)),
        w=int(rng.integers(1, 53)),
        m=MONTHS[int(rng.integers(12))],
        d=f"{int(rng.integers(1, 13)):02d}/{int(rng.integers(1, 29)):02d}",
    )


def _amounts(rng: np.random.Generator, n: int, total: float, sigma: float = 1.2) -> np.ndarray:
    raw = np.exp(rng.normal(0.0, sigma, n))
    return raw * total / raw.sum()


def _service_or_free(
    b: _Builder,
    world: World,
    vendor: VendorRecord,
    cat: Category,
    usd: float,
    natives: dict[str, list[str]],
    holdings_by_l2: dict[str, list[Holding]],
    kind: str,
    misc: bool = False,
) -> None:
    rng = b.rng
    native = (
        MISC_NATIVE[b.company] if misc else natives[cat.l2][int(rng.integers(len(natives[cat.l2])))]
    )
    if not cat.goods:
        description = _service_text(cat.l2, rng)[: b.style.desc_len].rstrip()
        if cat.l2 in HOURLY_L2:
            rate = float(rng.uniform(45, 220))
            qty = max(1.0, round(usd / rate))
            b.add(
                vendor=vendor,
                cat=cat,
                description=description,
                native=native,
                qty=qty,
                usd_price=usd / qty,
                kind=kind,
                uom="HR",
            )
            return
        uom = ("EA", "LOT", "")[int(rng.integers(3))]
        b.add(
            vendor=vendor,
            cat=cat,
            description=description,
            native=native,
            qty=1.0,
            usd_price=usd,
            kind=kind,
            uom=uom,
        )
        return
    pool = holdings_by_l2.get(cat.l2, [])
    holding = pool[int(rng.integers(len(pool)))] if pool else None
    description = free_text_description(cat, b.style, rng, holding)
    qty = float(rng.integers(1, 20)) if rng.random() < 0.6 else 1.0
    uom = ("EA", "LOT", "")[int(rng.integers(3))]
    b.add(
        vendor=vendor,
        cat=cat,
        description=description,
        native=native,
        qty=qty,
        usd_price=usd / qty,
        kind=kind,
        uom=uom,
    )


def _company_lines(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    world: World,
    company: str,
    style: Style,
    items: list[ItemView],
    vendors: list[VendorView],
    natives: dict[str, list[str]],
) -> list[dict]:
    shape = cfg.company(company)
    n_lines = cfg.count(shape.lines)
    total = shape.spend_usd * cfg.scale
    b = _Builder(cfg, rng, company, style, {id(v.record): v for v in vendors})
    cats = {c.l2: c for c in world.categories}
    pools: dict[str, list[VendorRecord]] = {}
    for v in world.vendors[company]:
        for l2 in v.parent.l2s:
            pools.setdefault(l2, []).append(v)

    n_service = int(round(cfg.service_line_share * n_lines))
    n_free = int(round(cfg.free_text_line_share * n_lines))
    n_spot = sum(1 for v in items if v.holding.spot)
    n_item = int(n_lines / (1.0 + cfg.return_line_rate)) - n_service - n_free - n_spot
    _item_lines(b, items, n_item, pools)

    holdings_by_l2: dict[str, list[Holding]] = {}
    for h in world.holdings[company]:
        holdings_by_l2.setdefault(h.item.category.l2, []).append(h)

    # Every vendor record has at least one line: idle vendors get one-off buys.
    used = {id(r["_vendor"]) for r in b.rows}
    idle = [v for v in world.vendors[company] if id(v) not in used]
    service_l2 = [c.l2 for c in world.categories if not c.goods]
    service_w = np.array([cats[l2].l1 == "L11" and 0.45 or 0.55 for l2 in service_l2])
    service_w = service_w * np.exp(rng.normal(0.0, 0.3, len(service_w)))
    service_budget = total * cfg.service_spend_share
    free_budget = total * cfg.free_text_spend_share
    idle_amounts = _amounts(rng, len(idle), 0.004 * total, 1.0) if idle else np.array([])
    for v, usd in zip(idle, idle_amounts, strict=True):
        l2 = v.parent.l2s[int(rng.integers(len(v.parent.l2s)))]
        kind = "service" if not cats[l2].goods else "free"
        _service_or_free(b, world, v, cats[l2], float(usd), natives, holdings_by_l2, kind)
        if kind == "service":
            service_budget -= float(usd)
        else:
            free_budget -= float(usd)

    # Services: L11 and L12, never item-coded.
    n_service_left = max(
        len(service_l2), n_service - sum(1 for v in idle if not cats[v.parent.l2s[0]].goods)
    )
    counts = rng.multinomial(n_service_left, service_w / service_w.sum())
    budgets = service_w / service_w.sum() * max(service_budget, 0.0)
    for l2, n, budget in zip(service_l2, counts, budgets, strict=True):
        pool = pools.get(l2, [])
        if n == 0 or not pool:
            continue
        w = np.array([v.weight for v in pool])
        picks = rng.choice(len(pool), size=int(n), p=w / w.sum())
        for idx, usd in zip(picks, _amounts(rng, int(n), float(budget)), strict=True):
            _service_or_free(
                b, world, pool[int(idx)], cats[l2], float(usd), natives, holdings_by_l2, "service"
            )

    # Goods bought on free text, spread like goods spend.
    goods_budget = world.budgets[company]
    n_free_left = max(1, n_free - len(idle))
    l2s = list(goods_budget)
    w = np.array([goods_budget[k] for k in l2s])
    counts = rng.multinomial(n_free_left, w / w.sum())
    misc_budget = cfg.unmapped_native_spend_share * total
    for l2, n in zip(l2s, counts, strict=True):
        pool = pools.get(l2, [])
        if n == 0 or not pool:
            continue
        budget = max(free_budget - misc_budget, 0.0) * goods_budget[l2] / w.sum()
        pw = np.array([v.weight for v in pool])
        picks = rng.choice(len(pool), size=int(n), p=pw / pw.sum())
        for idx, usd in zip(picks, _amounts(rng, int(n), budget), strict=True):
            _service_or_free(
                b, world, pool[int(idx)], cats[l2], float(usd), natives, holdings_by_l2, "free"
            )
    n_misc = max(1, int(round(0.01 * n_lines)))
    for usd in _amounts(rng, n_misc, misc_budget):
        l2 = l2s[int(rng.integers(len(l2s)))]
        pool = pools[l2]
        _service_or_free(
            b,
            world,
            pool[int(rng.integers(len(pool)))],
            cats[l2],
            float(usd),
            natives,
            holdings_by_l2,
            "free",
            misc=True,
        )

    # Returns and credits: a negative copy of a few item lines.
    item_rows = [r for r in b.rows if r["_kind"] == "item" and r["quantity"] >= 2]
    n_ret = int(round(cfg.return_line_rate * len(b.rows)))
    for i in sorted(
        rng.choice(len(item_rows), size=min(n_ret, len(item_rows)), replace=False).tolist()
    ):
        src = dict(item_rows[i])
        back = _round_qty(src["quantity"] * rng.uniform(0.1, 0.5), src["uom"])
        src["quantity"] = -min(back, src["quantity"] - 1)
        src["doc_date"] = min(src["doc_date"] + timedelta(int(rng.integers(3, 30))), cfg.period_end)
        src["_kind"] = "return"
        b.rows.append(src)
    return b.rows


def _greedy(rng: np.random.Generator, keys: list, weights: dict, target: float) -> list:
    """Pick keys in random order until their weight is as close as possible to ``target``."""
    chosen, acc = [], 0.0
    for i in rng.permutation(len(keys)):
        k = keys[int(i)]
        w = weights[k]
        if acc + w <= target or abs(acc + w - target) < abs(acc - target):
            chosen.append(k)
            acc += w
        if acc >= target:
            break
    return chosen


def build_lines(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    world: World,
    styles: dict[str, Style],
    items: dict[str, list[ItemView]],
    vendors: dict[str, list[VendorView]],
    natives: dict[str, dict[str, list[str]]],
) -> dict[str, pd.DataFrame]:
    """All purchase lines of both companies, with hidden truth columns."""
    for company in COMPANIES:
        views = items[company]
        n_spot = int(round(cfg.spot_buy_rate * len(views)))
        eligible = [v for v in views if not v.holding.trap]
        for i in rng.permutation(len(eligible))[:n_spot]:
            eligible[int(i)].holding.spot = True
    rows = {
        c: _company_lines(cfg, rng, world, c, styles[c], items[c], vendors[c], natives[c])
        for c in COMPANIES
    }
    view_of = {id(v.record): v for c in COMPANIES for v in vendors[c]}
    fx = cfg.fx()

    # Currency per vendor record: CA vendors invoice CAD, EU vendors EUR, until the shares are met.
    line_count: dict[tuple[str, int], int] = {}
    for c in COMPANIES:
        for r in rows[c]:
            key = (c, id(r["_vendor"]))
            line_count[key] = line_count.get(key, 0) + 1
    total_lines = sum(line_count.values())
    record_of = {(c, id(v.record)): v.record for c in COMPANIES for v in vendors[c]}
    keys = sorted(line_count, key=lambda k: (k[0], record_of[k].vendor_id))
    shares = dict(cfg.currency_shares)
    currency: dict[tuple[str, int], str] = {}
    for code, countries in (("CAD", {"CA"}), ("EUR", {"DE", "FR", "NL", "IT"})):
        cands = [k for k in keys if record_of[k].entity.country in countries]
        for k in _greedy(rng, cands, line_count, shares[code] * total_lines):
            currency[k] = code

    # Payment terms and incoterms per company-vendor; contracts per vendor on item spend.
    terms: dict[tuple[str, int], int] = {}
    incoterm: dict[tuple[str, int], str] = {}
    entity_incoterm: dict[str, str] = {}
    for k in keys:
        company, rec = k[0], record_of[k]
        options = cfg.payment_terms_choices[company]
        terms[k] = int(options[int(rng.choice(len(options), p=[p for _, p in options]))][0])
        prior = entity_incoterm.get(rec.entity.entity_id)
        if prior and rng.random() < 0.85:
            incoterm[k] = prior
        else:
            others = ("EXW", "FOB", "DAP", "DDP", "CPT")
            standard = rng.random() < cfg.standard_incoterm_rate
            incoterm[k] = (
                cfg.standard_incoterm if standard else others[int(rng.integers(len(others)))]
            )
        entity_incoterm.setdefault(rec.entity.entity_id, incoterm[k])

    item_spend: dict[tuple[str, int], float] = {}
    for c in COMPANIES:
        for r in rows[c]:
            if r["_kind"] in ("item", "spot", "return"):
                key = (c, id(r["_vendor"]))
                item_spend[key] = item_spend.get(key, 0.0) + r["quantity"] * r["_usd_price"]
    spend_keys = [k for k in keys if k in item_spend]
    target = cfg.contract_spend_share * sum(item_spend.values())
    contracts: dict[tuple[str, int], tuple[str, date]] = {}
    lo, hi = cfg.contract_end_months
    position = {k: i for i, k in enumerate(keys)}
    chosen = sorted(_greedy(rng, spend_keys, item_spend, target), key=position.__getitem__)
    for n, k in enumerate(chosen, start=1):
        months = int(rng.integers(lo, hi + 1))
        y, m = divmod(cfg.close_date.month - 1 + months, 12)
        end = date(cfg.close_date.year + y, m + 1, int(rng.integers(1, 29)))
        cid = (
            f"CTR-{int(rng.integers(2021, 2026))}-{n:04d}"
            if k[0] == "acquirer"
            else f"AGR{100000 + 7 * n}"
        )
        contracts[k] = (cid, end)

    frames = {}
    for c in COMPANIES:
        out = []
        for r in rows[c]:
            key = (c, id(r.pop("_vendor")))
            view = view_of[key[1]]
            cur = currency.get(key, "USD")
            rate = fx[cur]
            unit_price = round(r.pop("_usd_price") / rate, 4)
            qty = r["quantity"]
            amount = round(qty * unit_price, 2)
            doc_date: date = r["doc_date"]
            pay = ""
            if rng.random() < cfg.payment_date_rate:
                pay = (doc_date + timedelta(terms[key] + int(rng.normal(3, 6)))).isoformat()
            forced = r.pop("_incoterm")
            inc = forced or (incoterm[key] if rng.random() < cfg.incoterm_rate else "")
            contract = contracts.get(key) if r["_kind"] in ("item", "return") else None
            r.update(
                vendor_id=view.vendor_id,
                vendor_name=view.name,
                vendor_tax_id=view.tax_id,
                vendor_country=view.record.entity.country,
                unit_price=unit_price,
                line_amount=amount,
                currency=cur,
                payment_terms_days=terms[key],
                payment_date=pay,
                contract_id=contract[0] if contract else "",
                contract_end_date=contract[1].isoformat() if contract else "",
                incoterm=inc,
                doc_date=doc_date.isoformat(),
                _usd=amount * rate,
                _base_qty=qty * r["_base_per_unit"],
            )
            out.append(r)
        frames[c] = _po_numbers(pd.DataFrame(out), c)
    return frames


def _po_numbers(df: pd.DataFrame, company: str) -> pd.DataFrame:
    df["_seq"] = np.arange(len(df))
    df = df.sort_values(["doc_date", "vendor_id", "_seq"], kind="mergesort").reset_index(drop=True)
    po = df.groupby(["doc_date", "vendor_id"], sort=False).ngroup()
    line = df.groupby(po).cumcount() + 1
    if company == "acquirer":
        df["po_number"] = (4500010000 + po * 3).astype(str)
        df["po_line"] = (line * 10).astype(str)
    else:
        df["po_number"] = "PO" + (2500000 + po).astype(str).str.zfill(7)
        df["po_line"] = line.astype(str)
    return df.drop(columns="_seq")
