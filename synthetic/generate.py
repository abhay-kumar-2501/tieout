"""Generate one seeded demo dataset and write it to disk (PRD 8)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from synthetic import truth
from synthetic.config import COMPANIES, DEFAULT_CONFIG, GeneratorConfig
from synthetic.lines import OUTPUT_COLUMNS, build_lines
from synthetic.model import World
from synthetic.render import (
    MISC_NATIVE,
    ItemView,
    VendorView,
    make_style,
    native_categories,
    render_items,
    render_vendors,
)
from synthetic.world import build_world


@dataclass
class Dataset:
    seed: int
    config: GeneratorConfig
    world: World
    lines: dict[str, pd.DataFrame]  # with hidden ``_`` columns
    vendors: dict[str, list[VendorView]]
    items: dict[str, list[ItemView]]
    vendor_parents: pd.DataFrame
    category_map: pd.DataFrame
    truth_vendor_map: pd.DataFrame
    truth_item_map: pd.DataFrame
    truth_savings: pd.DataFrame
    truth_distractors: pd.DataFrame

    def purchase_lines(self, company: str) -> pd.DataFrame:
        """The company's input file exactly as written (PRD 3.1 columns)."""
        df = self.lines[company][OUTPUT_COLUMNS].copy()
        for col in ("quantity", "pack_qty"):
            df[col] = df[col].map(_clean_number).astype(object)
        return df


def _clean_number(x: object) -> object:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    value = float(x)  # type: ignore[arg-type]
    return int(value) if value.is_integer() else value


def generate(seed: int, scale: float = 1.0, config: GeneratorConfig | None = None) -> Dataset:
    """Build the true world, render both companies, add noise and write truth."""
    cfg = config or DEFAULT_CONFIG
    if scale != 1.0:
        cfg = cfg.scaled(scale)
    rng = np.random.default_rng(seed)
    world = build_world(cfg, rng)
    styles = {c: make_style(c, cfg, rng) for c in COMPANIES}
    vendors = render_vendors(world, cfg, rng)
    natives = native_categories(world, rng)
    items = render_items(world, cfg, styles, natives, rng)
    lines = build_lines(cfg, rng, world, styles, items, vendors, natives)
    return Dataset(
        seed=seed,
        config=cfg,
        world=world,
        lines=lines,
        vendors=vendors,
        items=items,
        vendor_parents=_vendor_parents(world, vendors, rng),
        category_map=_category_map(natives),
        truth_vendor_map=truth.vendor_map(vendors),
        truth_item_map=truth.item_map(items),
        truth_savings=truth.savings(world, lines),
        truth_distractors=truth.distractors(world, vendors, items),
    )


def _vendor_parents(
    world: World, vendors: dict[str, list[VendorView]], rng: np.random.Generator
) -> pd.DataFrame:
    """Hierarchy links no string comparison can find (PRD 3.2), from both vendor masters."""
    listed = {
        p.parent_id for p in world.parents if any(e.relation == "no_similarity" for e in p.entities)
    }
    rows: list[tuple[str, str, str, str]] = []
    for c in COMPANIES:
        for v in vendors[c]:
            parent = v.record.parent
            if parent.parent_id not in listed:
                continue
            country = v.record.entity.country
            if v.tax_id and rng.random() < 0.3:
                rows.append(("tax_id", v.tax_id, country, parent.name))
            else:
                rows.append(("name", v.name, country, parent.name))
    df = pd.DataFrame(rows, columns=["key_type", "key", "country", "parent_name"]).drop_duplicates()
    return df.sort_values(["parent_name", "key_type", "key"], kind="mergesort", ignore_index=True)


def _category_map(natives: dict[str, dict[str, list[str]]]) -> pd.DataFrame:
    rows = [
        (c, label, l2)
        for c in COMPANIES
        for l2, labels in natives[c].items()
        for label in labels
        if label != MISC_NATIVE[c]
    ]
    return pd.DataFrame(rows, columns=["company", "category_native", "l2_code"])


def write(ds: Dataset, out: Path, truth_dir: Path | None = None) -> dict[str, Path]:
    """Write inputs to ``out`` and truth to ``truth_dir`` (default ``out/truth``)."""
    out.mkdir(parents=True, exist_ok=True)
    truth_dir = truth_dir or out / "truth"
    truth_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "acquirer": out / "acquirer.csv",
        "target": out / "target.csv",
        "vendor_parents": out / "vendor_parents.csv",
        "category_map": out / "category_map.csv",
        "truth_vendor_map": truth_dir / "truth_vendor_map.csv",
        "truth_item_map": truth_dir / "truth_item_map.csv",
        "truth_savings": truth_dir / "truth_savings.csv",
        "truth_distractors": truth_dir / "truth_distractors.csv",
        "manifest": truth_dir / "manifest.json",
    }
    for company in COMPANIES:
        ds.purchase_lines(company).to_csv(paths[company], index=False, lineterminator="\n")
    for name in (
        "vendor_parents",
        "category_map",
        "truth_vendor_map",
        "truth_item_map",
        "truth_savings",
        "truth_distractors",
    ):
        getattr(ds, name).to_csv(paths[name], index=False, lineterminator="\n")
    manifest = {
        "seed": ds.seed,
        "scale": ds.config.scale,
        "memorable_unit_trap": ds.world.memorable_trap,
        "concentration_l2": ds.config.concentration_l2,
        "concentration_parent": ds.world.concentration_parent,
        "report_date": ds.config.report_date.isoformat(),
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return paths
