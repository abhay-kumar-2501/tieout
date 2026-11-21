"""Parent vendors, their legal entities and each company's vendor records (PRD 8.2)."""

from __future__ import annotations

import numpy as np

from synthetic.config import COMPANIES, GeneratorConfig
from synthetic.model import Category, Entity, Parent, VendorRecord, choice, weighted_l1
from synthetic.names import (
    COUNTRY_SUFFIX,
    DESCRIPTORS,
    GENERIC_WORDS,
    LEGAL_FORMS,
    NameFactory,
    is_denied,
    mutate_stem,
)

L1_VENDORS = {
    "L01": 0.09,
    "L02": 0.10,
    "L03": 0.08,
    "L04": 0.10,
    "L05": 0.12,
    "L06": 0.09,
    "L07": 0.08,
    "L08": 0.11,
    "L09": 0.09,
    "L10": 0.14,
}
DISTRIBUTOR_L1S = ("L02", "L03", "L04", "L05", "L06", "L07", "L09", "L10")
DISTRIBUTOR_WORDS = ("Industrial Supply", "Supply", "Distribution", "Industrial")
PAIR_WORDS = ("Works", "Group", "Industries", "Systems")
NO_SIM_WORDS = ("Direct", "Online", "Source", "Express", "Supply Hub", "Parts Direct")


class _VendorBuilder:
    def __init__(self, cfg: GeneratorConfig, rng: np.random.Generator, cats: list[Category]):
        self.cfg = cfg
        self.rng = rng
        self.names = NameFactory(rng)
        self.l2_by_l1: dict[str, list[str]] = {}
        for c in cats:
            self.l2_by_l1.setdefault(c.l1, []).append(c.l2)
        self.parents: list[Parent] = []
        self.entity_count = 0
        countries = cfg.country_shares
        self.countries = [c for c, _ in countries]
        self.country_p = [p for _, p in countries]

    def _tax_id(self, country: str) -> str:
        d = lambda n: "".join(str(int(x)) for x in self.rng.integers(0, 10, n))  # noqa: E731
        if country == "US":
            return f"{d(2)}-{d(7)}"
        if country == "CA":
            return f"{d(9)}RT0001"
        if country == "NL":
            return f"NL{d(9)}B01"
        if country == "IT":
            return f"IT{d(11)}"
        if country == "FR":
            return f"FR{d(2)}{d(9)}"
        return f"{country}{d(9)}"

    def _legal(self, country: str) -> str:
        return choice(self.rng, LEGAL_FORMS[country])

    def _compose(self, stem: str, l1: str, kind: str, country: str) -> str:
        rng = self.rng
        if kind == "distributor":
            body = f"{stem} {choice(rng, DISTRIBUTOR_WORDS)}"
        else:
            roll = rng.random()
            if roll < 0.10:
                body = stem
            elif roll < 0.16:
                body = f"{stem} & {self.names.stem()}"
            else:
                body = f"{stem} {choice(rng, DESCRIPTORS[l1])}"
                if rng.random() < 0.25:
                    body = f"{body} {choice(rng, GENERIC_WORDS)}"
        return f"{body} {self._legal(country)}"

    def _entity(self, parent_id: str, name: str, country: str, relation: str) -> Entity:
        self.entity_count += 1
        return Entity(
            f"TLE{self.entity_count:05d}", parent_id, name, country, self._tax_id(country), relation
        )

    def _l2s(self, l1: str, kind: str) -> list[str]:
        rng = self.rng
        if kind == "distributor":
            pool = [l2 for l1_ in DISTRIBUTOR_L1S for l2 in self.l2_by_l1[l1_]]
            n = int(rng.integers(6, 19))
            idx = sorted(rng.choice(len(pool), size=n, replace=False).tolist())
            return [pool[i] for i in idx]
        pool = self.l2_by_l1[l1]
        n = 1 + int(rng.random() < 0.55) + int(rng.random() < 0.25)
        if kind == "service":
            n = min(n, 2)
        idx = sorted(rng.choice(len(pool), size=min(n, len(pool)), replace=False).tolist())
        return [pool[i] for i in idx]

    def new_parent(
        self,
        companies: tuple[str, ...],
        *,
        kind: str | None = None,
        l1: str | None = None,
        name: str | None = None,
        stem: str | None = None,
        country: str | None = None,
        distractor: str = "",
    ) -> Parent:
        rng, cfg = self.rng, self.cfg
        if kind is None:
            roll = rng.random()
            kind = (
                "service"
                if roll < 0.20
                else "distributor"
                if roll < 0.20 + cfg.distributor_rate
                else "specialist"
            )
        if l1 is None:
            l1 = weighted_l1(rng, {"L11": 0.45, "L12": 0.55} if kind == "service" else L1_VENDORS)
        country = country or choice(rng, self.countries, self.country_p)
        while name is None:
            stem = self.names.stem()
            candidate = self._compose(stem, l1, kind, country)
            if not is_denied(candidate):
                name = candidate
        pid = f"TP{len(self.parents) + 1:05d}"
        weight = float(rng.pareto(1.15) + 0.05)
        parent = Parent(
            pid,
            name,
            stem or name.split()[0],
            l1,
            kind,
            self._l2s(l1, kind),
            companies,
            weight,
            distractor=distractor,
        )
        parent.entities.append(self._entity(pid, name, country, "main"))
        self.parents.append(parent)
        return parent

    def add_sibling(self, parent: Parent) -> None:
        rng = self.rng
        main = parent.entities[0]
        base = main.name.rsplit(" ", 1)[0]
        if rng.random() < 0.6:
            country = choice(rng, [c for c in self.countries if c != main.country])
            name = f"{base} {COUNTRY_SUFFIX.get(country, 'USA')} {self._legal(country)}"
        else:
            country = main.country
            region = choice(rng, ("West", "East", "South", "Central", "Midwest", "Atlantic"))
            name = f"{base} {region} {self._legal(country)}"
        parent.entities.append(self._entity(parent.parent_id, name, country, "sibling"))

    def add_no_similarity(self, parent: Parent) -> None:
        main = parent.entities[0]
        while True:
            name = (
                f"{self.names.stem()} {choice(self.rng, NO_SIM_WORDS)} {self._legal(main.country)}"
            )
            if not is_denied(name):
                break
        parent.entities.append(self._entity(parent.parent_id, name, main.country, "no_similarity"))

    def similar_pair(self, kind: str) -> tuple[Parent, Parent]:
        """Two unrelated parents with deceptively similar names (one per company)."""
        rng = self.rng
        descriptor_l1s = ("L01", "L02", "L03", "L05", "L06", "L07", "L08", "L09", "L11", "L12")
        stem = self.names.stem()
        legal = lambda: self._legal("US")  # noqa: E731
        if kind == "descriptor":
            l1a, l1b = (str(x) for x in rng.choice(descriptor_l1s, size=2, replace=False))
            name_a = f"{stem} {DESCRIPTORS[l1a][0]} {legal()}"
            name_b = f"{stem} {DESCRIPTORS[l1b][0]} {legal()}"
        elif kind == "stem":
            l1a = l1b = choice(rng, descriptor_l1s)
            other = mutate_stem(stem, rng)
            while not self.names.reserve(other):
                other = mutate_stem(stem, rng)
            words = f"{choice(rng, DESCRIPTORS[l1a])} {choice(rng, PAIR_WORDS)}"
            form = legal()
            name_a, name_b = f"{stem} {words} {form}", f"{other} {words} {form}"
        else:  # subset: "Apex" against "Apex Logistics"
            l1a, l1b = (str(x) for x in rng.choice(descriptor_l1s, size=2, replace=False))
            name_a = f"{stem} {legal()}"
            name_b = f"{stem} {DESCRIPTORS[l1b][0]} {legal()}"
        a = self.new_parent(
            ("acquirer",),
            kind="specialist",
            l1=l1a,
            name=name_a,
            stem=stem,
            country="US",
            distractor=kind,
        )
        b = self.new_parent(
            ("target",),
            kind="specialist",
            l1=l1b,
            name=name_b,
            stem=name_b.split()[0],
            country="US",
            distractor=kind,
        )
        return a, b


def build_vendors(
    cfg: GeneratorConfig, rng: np.random.Generator, cats: list[Category]
) -> tuple[list[Parent], dict[str, list[VendorRecord]], list[tuple[Parent, Parent, str]]]:
    vb = _VendorBuilder(cfg, rng, cats)
    overhead = 1.0 + cfg.duplicate_vendor_record_rate + 0.35 * cfg.multi_entity_parent_rate
    p_acq = cfg.count(cfg.acquirer.vendor_records) / overhead
    p_tgt = cfg.count(cfg.target.vendor_records) / overhead
    total = (p_acq + p_tgt) / (1.0 + cfg.shared_parent_rate)
    n_shared = int(round(cfg.shared_parent_rate * total))
    n_pairs = cfg.count(cfg.similar_vendor_pairs)
    n_acq_only = max(0, int(round(p_acq)) - n_shared - n_pairs)
    n_tgt_only = max(0, int(round(p_tgt)) - n_shared - n_pairs)

    pairs: list[tuple[Parent, Parent, str]] = []
    kinds = ("descriptor", "stem", "subset")
    for i in range(n_pairs):
        a, b = vb.similar_pair(kinds[i % 3])
        pairs.append((a, b, kinds[i % 3]))
    plan = (
        [("acquirer", "target")] * n_shared
        + [("acquirer",)] * n_acq_only
        + [("target",)] * n_tgt_only
    )
    order = rng.permutation(len(plan))
    for i in order:
        vb.new_parent(plan[int(i)])

    parents = vb.parents
    ordinary = [p for p in parents if not p.distractor]
    n_multi = int(round(cfg.multi_entity_parent_rate * len(parents)))
    n_nosim = int(round(cfg.no_similarity_parent_rate * len(parents)))
    picks = rng.permutation(len(ordinary))
    for i in picks[:n_multi]:
        vb.add_sibling(ordinary[int(i)])
        if rng.random() < 0.3:
            vb.add_sibling(ordinary[int(i)])
    for i in picks[n_multi : n_multi + n_nosim]:
        vb.add_no_similarity(ordinary[int(i)])

    _ensure_coverage(rng, parents, cats)
    return parents, _vendor_records(cfg, rng, parents), pairs


def _ensure_coverage(rng: np.random.Generator, parents: list[Parent], cats: list[Category]) -> None:
    """Every L2 gets at least three suppliers per company, and one shared one."""
    for cat in cats:
        for company in COMPANIES:
            have = [p for p in parents if company in p.companies and cat.l2 in p.l2s]
            pool = [
                p
                for p in parents
                if company in p.companies and p.l1 == cat.l1 and cat.l2 not in p.l2s
            ]
            pool = pool or [p for p in parents if company in p.companies and p.kind != "service"]
            while len(have) < 3 and pool:
                p = pool.pop(int(rng.integers(len(pool))))
                p.l2s.append(cat.l2)
                have.append(p)
        shared = [p for p in parents if p.shared and cat.l2 in p.l2s]
        if not shared:
            pool = [p for p in parents if p.shared and p.l1 == cat.l1 and not p.distractor]
            pool = pool or [p for p in parents if p.shared and not p.distractor]
            pool[int(rng.integers(len(pool)))].l2s.append(cat.l2)


def _vendor_records(
    cfg: GeneratorConfig, rng: np.random.Generator, parents: list[Parent]
) -> dict[str, list[VendorRecord]]:
    out: dict[str, list[VendorRecord]] = {c: [] for c in COMPANIES}
    multi = cfg.multi_entity_parent_rate + cfg.no_similarity_parent_rate
    cross = min(1.0, cfg.cross_entity_shared_rate / multi) if multi else 0.0
    for parent in parents:
        main = parent.entities[0]
        others = parent.entities[1:]
        for company in parent.companies:
            used = [main]
            if others:
                if parent.shared and company == "target" and rng.random() < cross:
                    used = [choice(rng, others)]  # target reaches the parent another way
                elif rng.random() < 0.3:
                    used.append(choice(rng, others))
            for entity in used:
                share = 1.0 if entity is used[0] else 0.35
                out[company].append(
                    VendorRecord(company, "", entity, parent, parent.weight * share)
                )
    for company in COMPANIES:
        records = out[company]
        n_dup = int(round(cfg.duplicate_vendor_record_rate * len(records)))
        for i in sorted(rng.choice(len(records), size=n_dup, replace=False).tolist()):
            src = records[i]
            records.append(
                VendorRecord(company, "", src.entity, src.parent, src.weight * 0.3, True)
            )
        order = rng.permutation(len(records))
        out[company] = [records[int(i)] for i in order]
    return out
