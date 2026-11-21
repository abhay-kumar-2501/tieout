"""The true world (PRD 8.2 step 1): vendors, items, who buys what at what price.

Nothing here knows how either company records its data; ``render`` does that.
Every random draw comes from the one generator passed in, and every loop runs
over lists in a fixed order, so a seed always produces the same world.
"""

from __future__ import annotations

import math

import numpy as np

from synthetic.catalog import Template, by_l2
from synthetic.config import COMPANIES, GeneratorConfig
from synthetic.model import (
    Category,
    Holding,
    Manufacturer,
    SharedItem,
    TrueItem,
    VendorRecord,
    World,
    choice,
    load_taxonomy,
)
from synthetic.names import NameFactory, is_denied
from synthetic.vendors import build_vendors

# Relative breadth (number of distinct items) and spend of each goods L1.
L1_ITEM_BREADTH = {
    "L01": 0.45,
    "L02": 2.2,
    "L03": 1.2,
    "L04": 1.4,
    "L05": 1.2,
    "L06": 1.3,
    "L07": 0.8,
    "L08": 0.55,
    "L09": 0.45,
    "L10": 0.9,
}
L1_SPEND = {
    "L01": 0.17,
    "L02": 0.07,
    "L03": 0.08,
    "L04": 0.09,
    "L05": 0.13,
    "L06": 0.06,
    "L07": 0.05,
    "L08": 0.09,
    "L09": 0.06,
    "L10": 0.08,
    "L11": 0.45,
    "L12": 0.55,
}
MFR_WORDS = {
    "L01": "Metals",
    "L02": "Fastener Works",
    "L03": "Bearing",
    "L04": "Valve",
    "L05": "Electric",
    "L06": "Abrasives",
    "L07": "Safety Products",
    "L08": "Packaging",
    "L09": "Chemical",
    "L10": "Tool",
}


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


def _manufacturers(rng: np.random.Generator, names: NameFactory) -> list[Manufacturer]:
    out: list[Manufacturer] = []
    prefixes: list[str] = []
    for l1, word in MFR_WORDS.items():
        for _ in range(9):
            while True:
                stem = names.stem()
                name = f"{stem} {word} {choice(rng, ('Inc', 'Co', 'Corp', 'LLC', 'GmbH', 'Ltd'))}"
                if not is_denied(name):
                    break
            prefix = stem[:3].upper()
            k = 3
            while prefix in prefixes:
                k += 1
                prefix = (stem[:2] + stem[k % len(stem)]).upper() + str(k)
            prefixes.append(prefix)
            out.append(Manufacturer(name, prefix, l1))
    return out


class _ItemFactory:
    def __init__(self, rng: np.random.Generator, mfrs: list[Manufacturer]):
        self.rng = rng
        self.mfrs_by_l1: dict[str, list[Manufacturer]] = {}
        for m in mfrs:
            self.mfrs_by_l1.setdefault(m.l1, []).append(m)
        self.templates = by_l2()
        self.seen: dict[tuple[str, tuple[str, ...]], str] = {}
        self.serials: dict[str, int] = {}
        self.items: list[TrueItem] = []

    def _cost(self, template: Template, values: tuple[str, ...]) -> float:
        cost = template.cost * math.exp(self.rng.normal(0.0, 0.30))
        for role, value in zip(template.roles, values, strict=True):
            if role.scale:
                cost *= 1.0 + template.scale_step * role.values.index(value)
        return round(cost, 6)

    def _mpn(self, mfr: Manufacturer, cat: Category) -> str:
        serial = self.serials.get(mfr.prefix, int(self.rng.integers(1000, 4000)))
        serial += int(self.rng.integers(1, 9))
        self.serials[mfr.prefix] = serial
        return f"{mfr.prefix}-{cat.l2[1:3]}{cat.l2[4:]}{serial:05d}"

    def _add(
        self,
        cat: Category,
        template: Template,
        values: tuple[str, ...],
        mfr: Manufacturer,
        sibling_of: str = "",
    ) -> TrueItem:
        item_id = f"TI{len(self.items) + 1:06d}"
        item = TrueItem(
            item_id,
            cat,
            template,
            values,
            self._cost(template, values),
            mfr,
            self._mpn(mfr, cat),
            sibling_of,
        )
        self.seen[(template.kind, values)] = item_id
        self.items.append(item)
        return item

    def new(self, cat: Category) -> TrueItem:
        rng = self.rng
        templates = self.templates[cat.l2]
        weights = [t.weight for t in templates]
        for _ in range(60):
            template = choice(rng, templates, weights)
            values = tuple(choice(rng, role.values) for role in template.roles)
            if (template.kind, values) not in self.seen:
                return self._add(cat, template, values, choice(rng, self.mfrs_by_l1[cat.l1]))
        raise RuntimeError(f"item pool exhausted for {cat.l2}")

    def sibling(self, item: TrueItem) -> TrueItem | None:
        """Same item but one critical attribute different (PRD 8.2 distractor)."""
        rng = self.rng
        template = item.template
        roles = list(range(len(template.roles)))
        rng.shuffle(roles)
        for r in roles:
            role = template.roles[r]
            current = item.values[r]
            options = [v for v in role.values if v != current]
            if not options:
                continue
            # Prefer a neighbouring value: the dangerous near-miss (M8X40 vs M8X45).
            pos = role.values.index(current)
            near = [v for v in options if abs(role.values.index(v) - pos) <= 2]
            for value in near + options:
                values = item.values[:r] + (value,) + item.values[r + 1 :]
                if (template.kind, values) not in self.seen:
                    sib = self._add(
                        item.category, template, values, item.manufacturer, item.item_id
                    )
                    sib.base_cost = round(item.base_cost * math.exp(rng.normal(0.0, 0.06)), 6)
                    return sib
        return None


def _breadth(goods: list[Category], factory: _ItemFactory, n_items: int) -> dict[str, float]:
    """Item-count weight per L2, capped so no L2 uses more than 40% of its attribute space."""
    pool = {
        c.l2: sum(math.prod(len(r.values) for r in t.roles) for t in factory.templates[c.l2])
        for c in goods
    }
    w = {
        c.l2: L1_ITEM_BREADTH[c.l1] * sum(t.weight for t in factory.templates[c.l2]) for c in goods
    }
    for _ in range(6):
        total = sum(w.values())
        w = {k: min(v, v * 0.4 * pool[k] / (n_items * v / total)) for k, v in w.items()}
    return w


def _l2_split(rng: np.random.Generator, n: int, weights: dict[str, float]) -> dict[str, int]:
    keys = list(weights)
    p = np.array([weights[k] for k in keys], dtype=float)
    counts = rng.multinomial(n, p / p.sum())
    return {k: int(c) for k, c in zip(keys, counts, strict=True)}


def build_world(cfg: GeneratorConfig, rng: np.random.Generator) -> World:
    cats = load_taxonomy()
    cat_by_l2 = {c.l2: c for c in cats}
    parents, vendors, pairs = build_vendors(cfg, rng, cats)
    mfrs = _manufacturers(rng, NameFactory(rng))
    factory = _ItemFactory(rng, mfrs)
    goods = [c for c in cats if c.goods]

    n_acq = cfg.count(cfg.acquirer.item_records)
    n_tgt = cfg.count(cfg.target.item_records)
    n_shared = int(round(cfg.shared_item_share * (n_acq + n_tgt) / 2))
    n_sib = min(cfg.count(cfg.near_identical_pairs), max(0, n_tgt - n_shared))
    breadth = _breadth(goods, factory, n_acq + n_tgt - n_shared)

    holdings: dict[str, list[Holding]] = {c: [] for c in COMPANIES}
    shared: list[SharedItem] = []
    for l2, n in _l2_split(rng, n_shared, breadth).items():
        for _ in range(n):
            item = factory.new(cat_by_l2[l2])
            pair = SharedItem(item, Holding("acquirer", item), Holding("target", item))
            shared.append(pair)
            holdings["acquirer"].append(pair.acquirer)
            holdings["target"].append(pair.target)
    for company, n in (("acquirer", n_acq - n_shared), ("target", n_tgt - n_shared - n_sib)):
        for l2, k in _l2_split(rng, n, breadth).items():
            for _ in range(k):
                holdings[company].append(Holding(company, factory.new(cat_by_l2[l2])))

    # Near-identical siblings: the target buys a one-attribute variant of an acquirer item.
    near: list[tuple[TrueItem, TrueItem]] = []
    shared_pool = [s.item for s in shared]
    shared_ids = {s.item_id for s in shared_pool}
    acq_only = [h.item for h in holdings["acquirer"] if h.item.item_id not in shared_ids]
    n_from_shared = int(round(cfg.near_identical_shared_share * n_sib))
    anchors = [shared_pool[int(i)] for i in rng.permutation(len(shared_pool))[:n_from_shared]]
    anchors += [acq_only[int(i)] for i in rng.permutation(len(acq_only))[: n_sib - len(anchors)]]
    for anchor in anchors:
        sib = factory.sibling(anchor)
        if sib is None:
            sib = factory.new(anchor.category)
        else:
            near.append((anchor, sib))
        holdings["target"].append(Holding("target", sib))

    budgets = _budgets(cfg, rng, cats)
    _assign_spend(cfg, rng, holdings, shared, budgets)
    _assign_mpn(cfg, rng, holdings, shared)
    _assign_vendors(cfg, rng, holdings, shared, vendors)
    conc_parent = _concentrate(cfg, rng, holdings, vendors)
    memorable = _plant_prices(cfg, rng, holdings, shared)
    _plant_packs(cfg, rng, holdings, shared)

    return World(
        cats,
        parents,
        vendors,
        mfrs,
        factory.items,
        holdings,
        shared,
        near,
        pairs,
        budgets,
        conc_parent,
        memorable,
    )


def _budgets(
    cfg: GeneratorConfig, rng: np.random.Generator, cats: list[Category]
) -> dict[str, dict[str, float]]:
    """Goods item spend per company and L2 (free text and services are budgeted in ``lines``)."""
    out: dict[str, dict[str, float]] = {}
    item_share = 1.0 - cfg.service_spend_share - cfg.free_text_spend_share
    for company in COMPANIES:
        total = cfg.company(company).spend_usd * cfg.scale * item_share
        w = {c.l2: L1_SPEND[c.l1] * math.exp(rng.normal(0.0, 0.35)) for c in cats if c.goods}
        s = sum(w.values())
        out[company] = {k: total * v / s for k, v in w.items()}
    return out


def _assign_spend(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    holdings: dict[str, list[Holding]],
    shared: list[SharedItem],
    budgets: dict[str, dict[str, float]],
) -> None:
    raw: dict[int, float] = {}
    for pair in shared:
        w = math.exp(rng.normal(cfg.shared_spend_lift, 1.45))
        raw[id(pair.acquirer)] = w
        raw[id(pair.target)] = w**0.8 * math.exp(rng.normal(0.0, 0.7))
    for company in COMPANIES:
        by_l2: dict[str, list[Holding]] = {}
        for h in holdings[company]:
            by_l2.setdefault(h.item.category.l2, []).append(h)
            if id(h) not in raw:
                raw[id(h)] = math.exp(rng.normal(0.0, 1.45))
        for l2, group in by_l2.items():
            total = sum(raw[id(h)] for h in group)
            for h in group:
                h.spend = budgets[company][l2] * raw[id(h)] / total


def _assign_mpn(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    holdings: dict[str, list[Holding]],
    shared: list[SharedItem],
) -> None:
    done: set[int] = set()
    for pair in shared:
        roll = rng.random()
        if roll < cfg.mpn_both_sides_rate:
            pair.acquirer.has_mpn = pair.target.has_mpn = True
        elif roll < cfg.mpn_both_sides_rate + cfg.mpn_one_side_rate:
            (pair.acquirer if rng.random() < 0.5 else pair.target).has_mpn = True
        done.update((id(pair.acquirer), id(pair.target)))
    for company in COMPANIES:
        for h in holdings[company]:
            if id(h) not in done:
                h.has_mpn = bool(rng.random() < cfg.mpn_rate_unshared)
            if h.has_mpn and rng.random() < cfg.mpn_only_record_rate[company] / 0.6:
                h.mpn_only = True


def _pools(vendors: dict[str, list[VendorRecord]]) -> dict[tuple[str, str], list[VendorRecord]]:
    pools: dict[tuple[str, str], list[VendorRecord]] = {}
    for company, records in vendors.items():
        for v in records:
            for l2 in v.parent.l2s:
                pools.setdefault((company, l2), []).append(v)
    return pools


def _pick(rng: np.random.Generator, pool: list[VendorRecord]) -> VendorRecord:
    return choice(rng, pool, [v.weight for v in pool])


def _assign_vendors(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    holdings: dict[str, list[Holding]],
    shared: list[SharedItem],
    vendors: dict[str, list[VendorRecord]],
) -> None:
    pools = _pools(vendors)
    paired: set[int] = set()
    for pair in shared:
        l2 = pair.item.category.l2
        acq_pool = pools[("acquirer", l2)]
        tgt_pool = pools[("target", l2)]
        shared_pool = [v for v in acq_pool if v.parent.shared]
        if shared_pool and rng.random() < cfg.same_vendor_bias:
            pair.acquirer.vendor = _pick(rng, shared_pool)
        else:
            pair.acquirer.vendor = _pick(rng, acq_pool)
        parent = pair.acquirer.vendor.parent
        same = [v for v in tgt_pool if v.parent is parent]
        if same and rng.random() < cfg.same_parent_given_shared:
            pair.target.vendor = _pick(rng, same)
        else:
            others = [v for v in tgt_pool if v.parent is not parent] or tgt_pool
            pair.target.vendor = _pick(rng, others)
        paired.update((id(pair.acquirer), id(pair.target)))
    for company in COMPANIES:
        for h in holdings[company]:
            if id(h) in paired:
                continue
            pool = pools[(company, h.item.category.l2)]
            h.vendor = _pick(rng, pool)
            others = [v for v in pool if v.parent is not h.vendor.parent]
            if others and rng.random() < cfg.second_vendor_rate:
                h.second_vendor = _pick(rng, others)
                h.second_share = float(rng.uniform(0.15, 0.35))
                h.second_premium = float(rng.uniform(*cfg.second_vendor_premium))


def _concentrate(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    holdings: dict[str, list[Holding]],
    vendors: dict[str, list[VendorRecord]],
) -> str:
    """Give one shared parent most of one critical L2, so the cap visibly binds."""
    l2 = cfg.concentration_l2
    group = [h for c in COMPANIES for h in holdings[c] if h.item.category.l2 == l2]
    if not group:
        return ""
    spend: dict[str, float] = {}
    for h in group:
        assert h.vendor is not None
        if h.vendor.parent.shared:
            spend[h.vendor.parent.parent_id] = spend.get(h.vendor.parent.parent_id, 0.0) + h.spend
    pools = _pools(vendors)
    candidates = [p for p in sorted(spend, key=lambda k: (-spend[k], k))]
    for pid in candidates:
        recs = {
            c: [v for v in pools[(c, l2)] if v.parent.parent_id == pid and not v.duplicate]
            for c in COMPANIES
        }
        if all(recs.values()):
            break
    else:
        return ""
    total = sum(h.spend for h in group)
    held = sum(h.spend for h in group if h.vendor and h.vendor.parent.parent_id == pid)
    order = sorted(group, key=lambda h: (-h.spend, h.company, h.item.item_id))
    for h in order:
        if held >= cfg.concentration_share * total:
            break
        if h.vendor and h.vendor.parent.parent_id != pid:
            if held + h.spend > (cfg.concentration_share + 0.04) * total:
                continue
            h.vendor = recs[h.company][0]
            h.second_vendor = None
            held += h.spend
    # Too dominant already: move its smallest items to other suppliers.
    for h in reversed(order):
        if held <= (cfg.concentration_share + 0.04) * total:
            break
        if h.vendor and h.vendor.parent.parent_id == pid:
            others = [v for v in pools[(h.company, l2)] if v.parent.parent_id != pid]
            if others and held - h.spend >= (cfg.concentration_share - 0.08) * total:
                h.vendor = _pick(rng, others)
                held -= h.spend
    return pid


def _plant_prices(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    holdings: dict[str, list[Holding]],
    shared: list[SharedItem],
) -> str:
    """Company prices, planted gaps, unit traps and freight distractors."""
    for company in COMPANIES:
        for h in holdings[company]:
            h.price = h.item.base_cost * math.exp(rng.normal(0.0, 0.05))
    count_items = [
        s
        for s in shared
        if s.item.category.dimension == "count" and s.item.category.family != "ppe"
    ]
    order = [count_items[int(i)] for i in rng.permutation(len(count_items))]
    n_traps = cfg.count(cfg.unit_trap_count)
    n_freight = cfg.count(cfg.freight_gap_items)

    # The memorable trap: a high-spend item, recorded per pack of 12 as if each.
    memorable = ""
    pool = [s for s in order if s.item.category.l2 == cfg.memorable_trap_l2] or order
    if pool:
        star = max(pool, key=lambda s: (s.acquirer.spend + s.target.spend, s.item.item_id))
        star.target.spend = cfg.memorable_trap_spend_usd * cfg.scale
        star.acquirer.spend = max(star.acquirer.spend, 0.6 * star.target.spend)
        star.target.trap, star.target.pack_size = "unconverted", cfg.memorable_trap_factor
        star.cause, star.distractor = "unit_trap", "unit_trap"
        memorable = star.item.item_id
        order = [s for s in order if s is not star]
    for s in order[: n_traps - 1]:
        side = s.acquirer if rng.random() < 0.5 else s.target
        side.trap = "as_each" if rng.random() < cfg.unit_trap_as_each_share else "unconverted"
        side.pack_size = int(choice(rng, s.item.template.packs or (10, 12, 25, 50, 100)))
        if side.pack_size < 6:
            side.pack_size = 10
        s.cause, s.distractor = "unit_trap", "unit_trap"
    rest = [s for s in shared if not s.distractor]
    for i in rng.permutation(len(rest))[:n_freight]:
        s = rest[int(i)]
        s.cause, s.distractor = "freight_terms", "freight_terms"

    for s in shared:
        lo, hi = (s.acquirer, s.target) if rng.random() < 0.5 else (s.target, s.acquirer)
        hi.price = lo.price
        if s.distractor == "freight_terms":
            hi.price = lo.price * (1.0 + rng.uniform(*cfg.freight_premium))
            lo.incoterm = choice(rng, ("EXW", "FCA"))
            hi.incoterm = choice(rng, ("DDP", "DAP"))
            continue
        if s.distractor or rng.random() >= cfg.gap_item_rate:
            continue
        gap = cfg.price_gap_scale * cfg.gap_median * math.exp(rng.normal(0.0, cfg.gap_sigma))
        s.gap = float(min(gap, 0.9))
        hi.price = lo.price * (1.0 + s.gap)
        assert s.acquirer.vendor is not None and s.target.vendor is not None
        same = s.acquirer.vendor.parent is s.target.vendor.parent
        s.cause = "price_gap_same_vendor" if same else "price_gap_switch"
    return memorable


def _plant_packs(
    cfg: GeneratorConfig,
    rng: np.random.Generator,
    holdings: dict[str, list[Holding]],
    shared: list[SharedItem],
) -> None:
    """Pack-unit differences on shared items and pack buying on others (PRD 8.2)."""
    split = list(cfg.pack_info_split)
    eligible = [
        s
        for s in shared
        if not s.distractor
        and s.item.template.packs
        and s.item.category.dimension == "count"
        and s.item.category.family != "ppe"
    ]
    n_diff = min(len(eligible), int(round(cfg.pack_difference_rate * len(shared))))
    chosen = [eligible[int(i)] for i in rng.permutation(len(eligible))[:n_diff]]
    n_text = int(round(split[0] * n_diff))
    n_col = int(round(split[1] * n_diff))
    modes = ["text"] * n_text + ["column"] * n_col + ["none"] * (n_diff - n_text - n_col)
    for s, mode in zip(chosen, modes, strict=True):
        side = s.acquirer if rng.random() < 0.5 else s.target
        side.pack_size = int(choice(rng, s.item.template.packs))
        side.pack_mode = mode
    paired = {id(h) for s in shared for h in (s.acquirer, s.target)}
    for company in COMPANIES:
        for h in holdings[company]:
            if id(h) in paired or h.item.category.dimension != "count":
                continue
            packs = h.item.template.packs
            if packs and rng.random() < cfg.unshared_pack_rate:
                h.pack_size = int(choice(rng, packs))
                h.pack_mode = choice(rng, ["text", "column", "none"], split)
    for s in shared:
        for side in (s.acquirer, s.target):
            if side.trap == "unconverted":
                side.pack_mode = "none"
