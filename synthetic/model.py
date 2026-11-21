"""Entities of the true world: categories, vendors, items and who buys what."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from synthetic.catalog import Template

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "tieout" / "reference" / "taxonomy.csv"


@dataclass(frozen=True)
class Category:
    l1: str
    l1_name: str
    l2: str
    l2_name: str
    family: str
    dimension: str
    ctype: str
    criticality: str

    @property
    def goods(self) -> bool:
        return self.dimension != "time"


@dataclass
class Entity:
    entity_id: str
    parent_id: str
    name: str
    country: str
    tax_id: str
    relation: str  # main | sibling | no_similarity


@dataclass
class Parent:
    parent_id: str
    name: str
    stem: str
    l1: str
    kind: str  # specialist | distributor | service
    l2s: list[str]
    companies: tuple[str, ...]
    weight: float
    entities: list[Entity] = field(default_factory=list)
    distractor: str = ""

    @property
    def shared(self) -> bool:
        return len(self.companies) == 2


@dataclass
class VendorRecord:
    company: str
    vendor_id: str
    entity: Entity
    parent: Parent
    weight: float
    duplicate: bool = False


@dataclass(frozen=True)
class Manufacturer:
    name: str
    prefix: str
    l1: str


@dataclass
class TrueItem:
    item_id: str
    category: Category
    template: Template
    values: tuple[str, ...]
    base_cost: float
    manufacturer: Manufacturer
    mpn: str
    sibling_of: str = ""


@dataclass
class Holding:
    """One company buying one true item: becomes one item record."""

    company: str
    item: TrueItem
    spend: float = 0.0
    price: float = 0.0  # USD per base unit
    vendor: VendorRecord | None = None
    second_vendor: VendorRecord | None = None
    second_share: float = 0.0
    second_premium: float = 0.0
    has_mpn: bool = False
    mpn_only: bool = False
    pack_size: int = 0  # 0 = bought in a base or fixed-factor unit
    pack_mode: str = ""  # text | column | none (only when pack_size > 0)
    trap: str = ""  # as_each | unconverted
    incoterm: str = ""  # forced incoterm (freight distractors)
    spot: bool = False


@dataclass
class SharedItem:
    item: TrueItem
    acquirer: Holding
    target: Holding
    gap: float = 0.0  # planted relative gap of the dearer side
    cause: str = "none"
    distractor: str = ""


@dataclass
class World:
    categories: list[Category]
    parents: list[Parent]
    vendors: dict[str, list[VendorRecord]]
    manufacturers: list[Manufacturer]
    items: list[TrueItem]
    holdings: dict[str, list[Holding]]
    shared: list[SharedItem]
    near_identical: list[tuple[TrueItem, TrueItem]]
    similar_vendor_pairs: list[tuple[Parent, Parent, str]]
    budgets: dict[str, dict[str, float]]  # company -> L2 -> goods item spend
    concentration_parent: str
    memorable_trap: str


def load_taxonomy(path: Path = TAXONOMY_PATH) -> list[Category]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            Category(
                r["l1_code"],
                r["l1_name"],
                r["l2_code"],
                r["l2_name"],
                r["family"],
                r["uom_dimension"],
                r["category_type"],
                r["criticality"],
            )
            for r in csv.DictReader(handle)
        ]


def choice(rng: np.random.Generator, options: list | tuple, p: list[float] | None = None):
    if p is not None:
        weights = np.asarray(p, dtype=float)
        return options[int(rng.choice(len(options), p=weights / weights.sum()))]
    return options[int(rng.integers(len(options)))]


def weighted_l1(rng: np.random.Generator, table: dict[str, float]) -> str:
    keys = list(table)
    return choice(rng, keys, [table[k] for k in keys])
