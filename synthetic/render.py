"""Each company's view of the true world (PRD 8.2 step 2): its ERP style.

The acquirer ("style A") writes descriptions adjective-first with spaces, keeps
legal names in title case, records imperial units and keeps punctuation in tax
IDs. The target ("style B") writes noun-first comma-separated text, abbreviates
heavily, truncates names at 30 and descriptions at 40 characters, prefers metric
units and strips tax IDs to alphanumerics. Item codes are unrelated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from synthetic.abbreviations import ABBREVIATIONS, by_expansion
from synthetic.catalog import NON_CRITICAL_ROLES, NOUN_HEAD, PARSER_FAMILIES, format_role
from synthetic.config import COMPANIES, GeneratorConfig
from synthetic.model import Category, Holding, VendorRecord, World
from synthetic.names import NAME_ABBREVIATIONS
from synthetic.noise import alias_variant, render_tax_id, truncate, upper_style, with_typo

STYLE_KEY = {"acquirer": "A", "target": "B"}
L1_CODE_PREFIX = {
    "L01": "RM",
    "L02": "FA",
    "L03": "BR",
    "L04": "PV",
    "L05": "EL",
    "L06": "CT",
    "L07": "SF",
    "L08": "PK",
    "L09": "CH",
    "L10": "MR",
}
# Recorded units per dimension: (uom, true base units per recorded unit, weight).
UNITS = {
    "A": {
        "length": (("FT", 0.3048, 1.0),),
        "mass": (("LB", 0.45359237, 1.0),),
        "volume": (("GAL", 3.785411784, 0.85), ("L", 1.0, 0.15)),
        "count": (("EA", 1.0, 1.0),),
    },
    "B": {
        "length": (("M", 1.0, 0.6), ("MTR", 1.0, 0.4)),
        "mass": (("KG", 1.0, 1.0),),
        "volume": (("L", 1.0, 0.7), ("LT", 1.0, 0.3)),
        "count": (("EA", 1.0, 0.7), ("PC", 1.0, 0.3)),
    },
}
PACK_UNITS = {
    "A": (("BX", 0.7), ("CS", 0.2), ("PK", 0.1)),
    "B": (("BX", 0.4), ("PK", 0.4), ("CS", 0.2)),
}
PACK_WORDS = {"BX": "BOX", "CS": "CASE", "PK": "PACK"}
MISC_NATIVE = {
    "acquirer": "ZZ99 - Miscellaneous / unclassified",
    "target": "9999-99 MISC NON CATALOG",
}


@dataclass
class Style:
    company: str
    key: str
    desc_len: int
    name_len: int
    habits: dict[str, tuple[str, float]]  # expansion -> (abbreviation, probability)
    expand: dict[str, tuple[str, float]]  # abbreviation -> (expansion, probability)


@dataclass
class VendorView:
    record: VendorRecord
    vendor_id: str
    name: str
    tax_id: str
    noise: str


@dataclass
class ItemView:
    holding: Holding
    item_code: str
    mpn: str
    manufacturer: str
    description: str
    uom: str
    base_per_unit: float  # true base units per recorded unit
    pack_qty: float | None
    category_native: str


def _pick(rng: np.random.Generator, options: tuple) -> object:
    return options[int(rng.integers(len(options)))]


def _weighted(rng: np.random.Generator, options: tuple[tuple, ...]) -> tuple:
    w = np.array([o[-1] for o in options], dtype=float)
    return options[int(rng.choice(len(options), p=w / w.sum()))]


def make_style(company: str, cfg: GeneratorConfig, rng: np.random.Generator) -> Style:
    key = STYLE_KEY[company]
    habits: dict[str, tuple[str, float]] = {}
    for expansion, abbrs in by_expansion().items():
        if key == "A":
            prob = float(rng.uniform(0.3, 0.7)) if rng.random() < 0.5 else 0.0
            habits[expansion] = (abbrs[0], prob)
        else:
            habits[expansion] = (str(_pick(rng, abbrs)), float(rng.uniform(0.6, 0.95)))
    expand_p = 0.12 if key == "A" else 0.3
    expand = {abbr: (exp, expand_p) for abbr, exp in ABBREVIATIONS if " " in exp or len(abbr) <= 3}
    return Style(
        company,
        key,
        cfg.acquirer_description_length if key == "A" else cfg.target_description_length,
        cfg.acquirer_name_length if key == "A" else cfg.target_name_length,
        habits,
        expand,
    )


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


def render_vendors(
    world: World, cfg: GeneratorConfig, rng: np.random.Generator
) -> dict[str, list[VendorView]]:
    """Vendor master of each company, with alias, typo, truncation and tax-ID noise."""
    both = {v.entity.entity_id for v in world.vendors["acquirer"] if not v.duplicate} & {
        v.entity.entity_id for v in world.vendors["target"] if not v.duplicate
    }
    alias_side: dict[str, str] = {}
    for entity_id in sorted(both):
        if rng.random() < cfg.alias_rate_shared:
            alias_side[entity_id] = COMPANIES[int(rng.integers(2))]

    out: dict[str, list[VendorView]] = {}
    for company in COMPANIES:
        key = STYLE_KEY[company]
        length = cfg.acquirer_name_length if key == "A" else cfg.target_name_length
        next_id = 10010 if key == "A" else 200000
        views = []
        for record in world.vendors[company]:
            next_id += int(rng.integers(1, 8 if key == "A" else 14))
            vendor_id = f"V{next_id:05d}" if key == "A" else f"{next_id:06d}"
            name, noise = record.entity.name, []
            if (
                key == "A"
                and rng.random() < 0.3
                and name.rsplit(" ", 1)[-1] in ("Inc", "Ltd", "LLC")
            ):
                name = name.rsplit(" ", 1)[0] + ", " + name.rsplit(" ", 1)[1] + "."
            if record.duplicate or alias_side.get(record.entity.entity_id) == company:
                name, kind = alias_variant(name, rng)
                noise.append(kind)
            if rng.random() < cfg.typo_rate:
                name = with_typo(name, rng)
                noise.append("typo")
            if key == "B":
                name = upper_style(name)
            if len(name) > length:
                noise.append("truncated")
            name = truncate(name, length)
            tax = record.entity.tax_id
            missing = rng.random() < cfg.tax_id_missing_rate
            tax_view = "" if missing else render_tax_id(tax, key)
            record.vendor_id = vendor_id
            views.append(VendorView(record, vendor_id, name, tax_view, "+".join(noise)))
        out[company] = views
    return out


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


def _abbreviate(words: list[str], style: Style, rng: np.random.Generator) -> list[str]:
    expanded: list[str] = []
    for w in words:
        hit = style.expand.get(w)
        if hit and rng.random() < hit[1]:
            expanded.extend(hit[0].split())
        else:
            expanded.append(w)
    out: list[str] = []
    i = 0
    while i < len(expanded):
        for size in (4, 3, 2, 1):
            phrase = " ".join(expanded[i : i + size])
            hit = style.habits.get(phrase) if i + size <= len(expanded) else None
            if hit and hit[1] > 0 and rng.random() < hit[1]:
                out.append(hit[0])
                i += size
                break
        else:
            out.append(expanded[i])
            i += 1
    return out


def pack_phrase(
    n: int, unit: str, style_key: str, parseable: bool, rng: np.random.Generator
) -> str:
    """Pack size as written in a description; only ``parseable`` forms match PRD 3.5."""
    word = PACK_WORDS[unit]
    if not parseable:
        return str(_pick(rng, (f"{n}/CTN", f"{n} CT", f"CTN {n}", f"{n} PIECES")))
    if style_key == "A":
        return str(_pick(rng, (f"{unit}/{n}", f"{word} OF {n}", f"{n}/{unit}")))
    return str(_pick(rng, (f"{n}/{unit}", f"{n} PCS/{unit}", f"{n} PER {word}", f"{unit} {n}")))


def describe(holding: Holding, style: Style, rng: np.random.Generator, suffix: str = "") -> str:
    """Render a true item's description in an ERP style."""
    item = holding.item
    template, family = item.template, item.category.family
    parser = family in PARSER_FAMILIES
    segs: list[tuple[str, bool]] = []  # (text, critical)
    for role, value in zip(template.roles, item.values, strict=True):
        text = format_role(role, value, style.key, family)
        if role.fmt != "desig":
            text = " ".join(_abbreviate(text.split(), style, rng))
        if role.fmt == "x" and segs:
            joined = segs[-1][0] + (" X " if style.key == "B" and parser else "X") + text
            segs[-1] = (joined, True)
        else:
            segs.append((text, role.name not in NON_CRITICAL_ROLES))
    words = list(template.noun)
    if style.key == "A":
        noun, sep = " ".join(_abbreviate(words, style, rng)), " "
    else:
        sep = ","
        whole = _abbreviate(words, style, rng)
        if len(whole) == 1 and len(words) > 1:  # "HEX HEAD CAP SCREW" -> "HHCS"
            noun = whole[0]
        else:
            h = NOUN_HEAD.get(template.kind, len(words) - 1)
            mods = words[:h] + words[h + 1 :]
            noun = " ".join(_abbreviate([words[h]], style, rng))
            if mods:
                noun += "," + " ".join(_abbreviate(mods, style, rng))
        if len(segs) > 2 and rng.random() < 0.4:
            segs = segs[1:2] + segs[:1] + segs[2:]  # the target's clerks often lead with the size
    limit = style.desc_len - (len(suffix) + 1 if suffix else 0)
    # A full field: the clerk drops optional words first, unless they just type on.
    if style.key == "A" or rng.random() < 0.75:
        while len(sep.join([noun] + [s for s, _ in segs])) > limit and any(not c for _, c in segs):
            drop = max(i for i, (_, c) in enumerate(segs) if not c)
            segs = segs[:drop] + segs[drop + 1 :]
    body = truncate(sep.join([noun] + [s for s, _ in segs]), limit)
    return body + sep + suffix if suffix else body


def _manufacturer_view(
    holding: Holding, key: str, cfg: GeneratorConfig, rng: np.random.Generator
) -> str:
    name = holding.item.manufacturer.name
    if not holding.mpn_only and rng.random() < cfg.manufacturer_blank_rate:
        return ""
    if key == "A":
        return name
    words = name.upper().split()[:-1]  # the target drops the legal form
    if rng.random() < cfg.manufacturer_abbreviated_rate:
        abbr = {k.upper(): v.upper() for k, v in NAME_ABBREVIATIONS.items()}
        words = [abbr.get(w, w) for w in words] if len(words) > 1 else words
        words = words[:1] if rng.random() < 0.5 else words
    return " ".join(words)


def _mpn_view(mpn: str, key: str, rng: np.random.Generator) -> str:
    if key == "A":
        return mpn
    return mpn.replace("-", "") if rng.random() < 0.7 else mpn.replace("-", " ")


def native_categories(world: World, rng: np.random.Generator) -> dict[str, dict[str, list[str]]]:
    """company -> L2 -> native category labels (one or two per L2)."""
    out: dict[str, dict[str, list[str]]] = {}
    for company in COMPANIES:
        labels: dict[str, list[str]] = {}
        seq: dict[str, int] = {}
        for cat in world.categories:
            if company == "acquirer":
                prefix = L1_CODE_PREFIX.get(cat.l1, "SV")
                seq[prefix] = seq.get(prefix, 0) + 1
                base = f"{prefix}{seq[prefix]:02d} - {cat.l2_name}"
                if cat.goods and rng.random() < 0.3:
                    labels[cat.l2] = [f"{base} (production)", f"{base} (MRO)"]
                else:
                    labels[cat.l2] = [base]
            else:
                code = 3000 + 100 * int(cat.l1[1:]) + 10 * int(cat.l2[4:])
                words = cat.l2_name.upper().replace("&", "").replace(",", "").split()
                labels[cat.l2] = [f"{code}-{int(rng.integers(10, 99))} {' '.join(words)[:24]}"]
        out[company] = labels
    return out


def _unit(
    cat: Category, holding: Holding, key: str, rng: np.random.Generator
) -> tuple[str, float, float | None, str]:
    """(uom, true base units per recorded unit, pack_qty column, pack phrase)."""
    if holding.trap == "as_each":
        return "EA", float(holding.pack_size), None, ""
    if holding.pack_size:
        unit = str(_weighted(rng, PACK_UNITS[key])[0])
        mode = holding.pack_mode
        phrase = ""
        if mode == "text":
            phrase = pack_phrase(holding.pack_size, unit, key, True, rng)
        elif mode == "none" and holding.trap != "unconverted" and rng.random() < 0.5:
            phrase = pack_phrase(holding.pack_size, unit, key, False, rng)
        pack_qty = float(holding.pack_size) if mode == "column" else None
        return unit, float(holding.pack_size), pack_qty, phrase
    if cat.family == "ppe" and holding.item.template.kind.endswith("_glove") and key == "A":
        if holding.item.template.kind != "nitrile_glove":
            return "PR", 1.0, None, ""
    uom, factor, _ = _weighted(rng, UNITS[key][cat.dimension])
    return str(uom), float(factor), None, ""


def render_items(
    world: World,
    cfg: GeneratorConfig,
    styles: dict[str, Style],
    natives: dict[str, dict[str, list[str]]],
    rng: np.random.Generator,
) -> dict[str, list[ItemView]]:
    out: dict[str, list[ItemView]] = {}
    for company in COMPANIES:
        style = styles[company]
        key = style.key
        holdings = world.holdings[company]
        counters: dict[str, int] = {}
        code_next = 30000000
        views: list[ItemView] = []
        for i in rng.permutation(len(holdings)):
            h = holdings[int(i)]
            cat = h.item.category
            if h.mpn_only:
                code = ""
            elif key == "A":
                prefix = L1_CODE_PREFIX[cat.l1]
                counters[prefix] = counters.get(prefix, 10000) + int(rng.integers(1, 6))
                code = f"{prefix}-{counters[prefix]:05d}"
            else:
                code_next += int(rng.integers(1, 40))
                code = f"{code_next:08d}"
            uom, factor, pack_qty, phrase = _unit(cat, h, key, rng)
            description = describe(h, style, rng, phrase)
            mpn = _mpn_view(h.item.mpn, key, rng) if h.has_mpn else ""
            manufacturer = (
                _manufacturer_view(h, key, cfg, rng) if (h.has_mpn or rng.random() < 0.4) else ""
            )
            native = natives[company][cat.l2]
            views.append(
                ItemView(
                    h,
                    code,
                    mpn,
                    manufacturer,
                    description,
                    uom,
                    factor,
                    pack_qty,
                    str(_pick(rng, tuple(native))),
                )
            )
        out[company] = views
    return out


def free_text_description(
    cat: Category, style: Style, rng: np.random.Generator, holding: Holding | None
) -> str:
    """Goods bought on free text: no item code, no MPN."""
    if holding is not None and rng.random() < 0.5:
        return describe(holding, style, rng)
    noun = cat.l2_name.upper().replace("&", "AND").replace(",", "")
    ref = int(rng.integers(1000, 99999))
    text = str(
        _pick(
            rng,
            (
                f"MISC {noun} PER QUOTE {ref}",
                f"{noun} - SPOT PURCHASE REF {ref}",
                f"REPAIR SERVICE {noun} WO {ref}",
                f"{noun} AS PER DRAWING {ref}",
                f"EMERGENCY BUY {noun}",
                f"{noun} SUNDRY ITEMS",
            ),
        )
    )
    return truncate(text, style.desc_len)
