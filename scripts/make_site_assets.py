"""Write the landing page's sample outputs and figures to ``site/`` (PRD 7.3, 9.2, 9.4).

Run by ``make demo`` after the sample results are written. It reads the sample
manifest (``data/samples.json``), each sample's committed results and the
held-out scorecard, and writes, per sample, the bridge image, the sample
workbook and the sample deck (all in the clean-team view), then regenerates
``site/data.js`` from the same files. The first sample (the held-out demo seed)
keeps the original paths under ``site/assets/``; the others go to
``site/assets/samples/<id>/``. It never writes to ``data/``.

Run: ``python scripts/make_site_assets.py [--manifest FILE] [--scorecard FILE] [--site DIR]``
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_JS_HEADER = (
    "// Regenerated from data/samples.json, each sample's results (results.json and "
    "the result tables) and data/demo/scorecard.json.\n"
)
ASSET_NAMES = {
    "bridge": "bridge.png",
    "workbook": "tieout_workbook.xlsx",
    "deck": "tieout_deck.pptx",
}


def asset_paths(sample_id: str, first: bool) -> dict[str, str]:
    """Site-relative paths of one sample's three downloads."""
    folder = "assets/" if first else f"assets/samples/{sample_id}/"
    return {key: folder + name for key, name in ASSET_NAMES.items()}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["samples"]


def sample_object(
    sample: dict[str, Any], results_json: dict, first: bool, story: dict | None = None
) -> dict:
    """One sample's figures, as the landing page reads them."""
    totals = results_json["totals"]
    lever1 = totals["lever1"]
    row = {
        "id": sample["id"],
        "label": sample["label"],
        "naive": lever1["naive"],
        "defensible_recurring": totals["recurring"],
        "lever1": {
            "defensible": lever1["bridge"]["defensible"],
            "steps": [lever1["bridge_raw"][f"step_{i}"] for i in range(1, 8)],
        },
        "assets": asset_paths(sample["id"], first),
    }
    if story is not None:
        row["story"] = story
    return row


# ------------------------------------------------------------------ the page's story
#
# The landing page tells the story with real records from each sample's results: how
# much the two companies buy in common, one pair of records that is the same item
# written differently, one pair that looks alike but is not, and one price gap that is
# really a unit difference. Everything below reads the committed result tables; no
# record is invented or edited.

_TOKEN_SPLIT = re.compile(r"([\s,;]+)")
_NUMBER = re.compile(r"(?<![\d./])\d+(?:\.\d+)?(?![\d./])")
_DIFFERING_NUMBERS = re.compile(r"Other numbers in the descriptions differ \(([^)]*) vs ([^)]*)\)")
MAX_DESCRIPTION = 46  # characters: an example must fit a phone-width card


def _clean_text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _split(text: str) -> list[str]:
    """Words and the separators between them, so that ``"".join`` gives ``text`` back."""
    return [part for part in _TOKEN_SPLIT.split(text) if part]


def _is_word(part: str) -> bool:
    return not _TOKEN_SPLIT.fullmatch(part)


class _Groups:
    """Union-find over (side, index) word positions, remembering why two words link."""

    def __init__(self) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {}
        self.kind: dict[tuple[int, int], str] = {}

    def find(self, x: tuple[int, int]) -> tuple[int, int]:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def union(self, a: tuple[int, int], b: tuple[int, int], kind: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
        # One link that is not a plain repeat makes the whole group worth explaining.
        root = self.find(a)
        if self.kind.get(root, "same") == "same":
            self.kind[root] = kind
        for r in (ra, rb):
            if r != root and self.kind.get(r, "same") != "same":
                self.kind[root] = self.kind[r]


def _link_words(
    parts: tuple[list[str], list[str]], meanings: tuple[list[set[str]], list[set[str]]]
) -> tuple[list[list[Any]], list[list[Any]], list[dict[str, str]]]:
    """Tag each word of two texts with the group of words it agrees with on the other side.

    Two words agree when they mean the same after normalisation (case, abbreviations,
    legal forms), or one is a typing slip or an abbreviation of the other. Returns each
    side as ``[[text, group], ...]`` (group 0 = no counterpart) and one note per group
    that needed more than a plain repeat to read.
    """
    from tieout.normalise.spelling import is_abbreviation, is_typing_slip

    groups = _Groups()
    for i, word_a in enumerate(parts[0]):
        if not meanings[0][i]:
            continue
        for j, word_b in enumerate(parts[1]):
            if not meanings[1][j]:
                continue
            ua, ub = word_a.upper(), word_b.upper()
            if ua == ub:
                kind = "same"
            elif meanings[0][i] & meanings[1][j]:
                kind = "abbr" if meanings[0][i] != meanings[1][j] or len(ua) != len(ub) else "case"
                if ua.casefold() == ub.casefold():
                    kind = "case"
            elif ua.isalpha() and ub.isalpha() and min(len(ua), len(ub)) >= 4:
                if is_typing_slip(ua, ub):
                    kind = "slip"
                elif is_abbreviation(*sorted((ua, ub), key=len)) and min(len(ua), len(ub)) >= 3:
                    kind = "abbr"
                else:
                    continue
            else:
                continue
            groups.union((0, i), (1, j), kind)

    numbers: dict[tuple[int, int], int] = {}
    out: list[list[list[Any]]] = [[], []]
    for side in (0, 1):
        for i, word in enumerate(parts[side]):
            root = groups.find((side, i)) if (side, i) in groups.parent else None
            linked = root is not None and any(
                groups.find(k) == root and k[0] != side for k in groups.parent
            )
            if not linked:
                out[side].append([word, 0])
                continue
            numbers.setdefault(root, len(numbers) + 1)
            out[side].append([word, numbers[root]])

    notes = []
    for root, number in numbers.items():
        kind = groups.kind.get(root, "same")
        if kind == "same":
            continue
        a = " ".join(w for w, g in out[0] if g == number)
        b = " ".join(w for w, g in out[1] if g == number)
        if a.upper() == b.upper():
            kind = "case"
        elif any(ch.isdigit() for ch in a + b):
            kind = "format"  # the same size or number, written another way: 6IN / 6"
        notes.append({"kind": kind, "a": a, "b": b})
    return out[0], out[1], notes


def _with_separators(text: str, tagged: list[list[Any]]) -> list[list[Any]]:
    """Interleave the separators back, so the page can rebuild the exact text."""
    words = iter(tagged)
    return [next(words) if _is_word(p) else [p, 0] for p in _split(text)]


def _description_meanings(words: list[str]) -> list[set[str]]:
    from tieout.normalise.items import normalise_description

    return [set(normalise_description(w).split()) for w in words]


def _vendor_meanings(words: list[str], name: str) -> list[set[str]]:
    """A word's meaning is its normalised form, or nothing if normalisation drops it."""
    from tieout.normalise.vendors import normalise_name

    kept = set(normalise_name(name).split())
    return [set(normalise_name(w).split()) & kept for w in words]


def _tie_out(text_a: str, text_b: str, kind: str) -> dict[str, Any]:
    parts = ([p for p in _split(text_a) if _is_word(p)], [p for p in _split(text_b) if _is_word(p)])
    if kind == "vendor":
        meanings = (_vendor_meanings(parts[0], text_a), _vendor_meanings(parts[1], text_b))
    else:
        meanings = (_description_meanings(parts[0]), _description_meanings(parts[1]))
    tag_a, tag_b, notes = _link_words(parts, meanings)
    tokens_a, tokens_b = _with_separators(text_a, tag_a), _with_separators(text_b, tag_b)
    if kind == "vendor":
        # Words the normaliser drops (legal forms, "the") are shown as ignored.
        for tokens, words, mean in (
            (tokens_a, parts[0], meanings[0]),
            (tokens_b, parts[1], meanings[1]),
        ):
            dropped = {w for w, m in zip(words, mean, strict=True) if not m}
            for token in tokens:
                if token[1] == 0 and token[0] in dropped:
                    token[1] = -1
    return {"a": tokens_a, "b": tokens_b, "notes": notes}


def _mark_pack(tokens: list[list[Any]]) -> None:
    """Mark the words of a stated pack size ("BX/1000", "BOX OF 500") with group -2."""
    from tieout.normalise.packs import _find

    text = "".join(t for t, _ in tokens)
    match = _find(text.upper())
    if not match:
        return
    pos = 0
    for token in tokens:
        end = pos + len(token[0])
        if token[1] <= 0 and _is_word(token[0]) and pos < match.end() and end > match.start():
            token[1] = -2
        pos = end


def _mark_numbers(tokens: list[list[Any]], numbers: list[str]) -> None:
    """Mark the words carrying a number the engine found in conflict with group -3."""
    wanted = {n.strip() for n in numbers if n.strip()}
    for token in tokens:
        if _is_word(token[0]) and wanted & set(_NUMBER.findall(token[0])):
            token[1] = -3


def _item_records(results: Path) -> tuple[Any, Any]:
    """Per item record: description, main supplier, main unit and prices; and the lines."""
    import pandas as pd

    lines = pd.read_parquet(
        results / "lines.parquet",
        columns=[
            "company", "item_key", "vendor_name", "vendor_key", "uom", "unit_price_rc",
            "price_base", "base_unit", "conv_status", "amount", "canonical_item_id",
        ],
    )  # fmt: skip
    priced = lines[lines["item_key"].notna()].copy()
    priced["record"] = priced["company"] + ":" + priced["item_key"].astype(str)
    return priced, lines


def _record_card(priced: Any, record: str, description: str) -> dict[str, Any] | None:
    """The fields shown on one record card: the record's main supplier and unit."""
    rows = priced[priced["record"] == record]
    if rows.empty:
        return None
    vendor = rows.groupby("vendor_name")["amount"].sum().idxmax()
    rows = rows[rows["vendor_name"] == vendor]
    uom = rows.groupby("uom")["amount"].sum().idxmax()
    rows = rows[rows["uom"] == uom]
    base = rows["price_base"].dropna()
    return {
        "company": record.split(":", 1)[0],
        "vendor": str(vendor),
        "vendor_key": str(rows["vendor_key"].iloc[0]),
        "description": description,
        "uom": str(uom),
        "price": round(float(rows["unit_price_rc"].median()), 4),
        "price_base": round(float(base.median()), 4) if len(base) else None,
        "base_unit": _clean_text(rows["base_unit"].iloc[0]),
        "conv": str(rows["conv_status"].iloc[0]),
        "lines": int(len(rows)),
    }


def _pair_example(cards: tuple[dict, dict], pair: Any, kind: str) -> dict[str, Any]:
    vendor = _tie_out(cards[0]["vendor"], cards[1]["vendor"], "vendor")
    item = _tie_out(cards[0]["description"], cards[1]["description"], "item")
    for key in ("a", "b"):
        _mark_pack(item[key])
    if kind == "lookalike":
        m = _DIFFERING_NUMBERS.search(pair["evidence"])
        if m:
            _mark_numbers(item["a"], m.group(1).split(","))
            _mark_numbers(item["b"], m.group(2).split(","))
    same_supplier = cards[0].get("entity") is not None and cards[0]["entity"] == cards[1].get(
        "entity"
    )
    if not same_supplier:
        # Two different suppliers: a shared word such as "Industrial" proves nothing.
        vendor["notes"] = []
        for key in ("a", "b"):
            vendor[key] = [[text, 0] for text, _ in vendor[key]]
    a, b = ({k: v for k, v in c.items() if k not in ("vendor_key", "entity")} for c in cards)
    return {
        "kind": kind,
        "same_supplier": same_supplier,
        "a": a | {"vendor_tokens": vendor["a"], "item_tokens": item["a"]},
        "b": b | {"vendor_tokens": vendor["b"], "item_tokens": item["b"]},
        "notes": {"vendor": vendor["notes"], "item": item["notes"]},
        "stage": str(pair["stage"]),
        "tier": str(pair["tier"]),
        "similarity": round(float(pair["cosine"]), 2),
        "evidence": str(pair["evidence"]),
    }


def _candidate_cards(pair: Any, descriptions: dict, priced: Any, entities: dict) -> tuple | None:
    cards = []
    for key in (pair["key_a"], pair["key_b"]):
        text = descriptions.get(key)
        if not text or len(text) > MAX_DESCRIPTION:
            return None
        card = _record_card(priced, key, text)
        if card is None:
            return None
        card["entity"] = entities.get(card["vendor_key"])
        cards.append(card)
    return tuple(cards)


def _match_example(pairs: Any, descriptions: dict, priced: Any, entities: dict) -> dict | None:
    """A tier-B pair (matched on the description) that reads differently on both sides.

    Preferred: the same supplier under two spellings, abbreviations to read through, a
    per-unit price on both sides, and most words accounted for.
    """
    best, best_key = None, None
    rows = pairs[(pairs["tier"] == "B") & (pairs["status"] == "auto")]
    for _, pair in rows.sort_values("pair_id").iterrows():
        cards = _candidate_cards(pair, descriptions, priced, entities)
        if cards is None or cards[0]["price_base"] is None or cards[1]["price_base"] is None:
            continue
        if cards[0]["base_unit"] != cards[1]["base_unit"]:
            continue
        low, high = sorted((cards[0]["price_base"], cards[1]["price_base"]))
        if low <= 0 or high / low > 2:
            continue  # a wild gap is a unit problem, which is the trap's story, not this one
        example = _pair_example(cards, pair, "match")
        item_notes = [n for n in example["notes"]["item"] if n["kind"] in ("abbr", "slip")]
        words = [t for side in "ab" for t in example[side]["item_tokens"] if _is_word(t[0])]
        coverage = sum(1 for t in words if t[1] > 0 or t[1] == -2) / len(words)
        vendor_differs = cards[0]["vendor"] != cards[1]["vendor"]
        key = (
            example["same_supplier"] and vendor_differs,
            bool(example["notes"]["vendor"]),
            min(len(item_notes), 3),
            round(coverage, 1),
        )
        if best_key is None or key > best_key:
            best, best_key = example, key
    return best


def _lookalike_example(pairs: Any, descriptions: dict, priced: Any, entities: dict) -> dict | None:
    """A review-only pair that reads alike but carries a different number (a different item)."""
    rows = pairs[(pairs["tier"] == "C") & pairs["number_mismatch"].astype(bool)]
    rows = rows[rows["evidence"].str.contains("Other numbers in the descriptions differ")]
    for _, pair in rows.sort_values(["cosine", "pair_id"], ascending=[False, True]).iterrows():
        m = _DIFFERING_NUMBERS.search(pair["evidence"])
        if not m or "0" in (m.group(1).strip(), m.group(2).strip()):
            continue
        cards = _candidate_cards(pair, descriptions, priced, entities)
        if cards is None:
            continue
        example = _pair_example(cards, pair, "lookalike")
        if all(any(t[1] == -3 for t in example[s]["item_tokens"]) for s in "ab"):
            return example
    return None


def _trap_example(results: Path, priced: Any, item_map: Any, entities: dict) -> dict | None:
    """The item whose unit difference the naive figure counted as the largest saving.

    Taken from bridge step 1 (unit-of-measure errors): the item with the most dollars
    removed whose two companies record it in different units.
    """
    import pandas as pd

    detail = pd.read_parquet(results / "bridge_detail.parquet")
    removed = (
        detail[detail["step"] == 1]
        .groupby("canonical_item_id")["amount_removed"]
        .sum()
        .sort_values(ascending=False)
    )
    records = item_map[item_map["canonical_item_id"].notna()]
    for item, amount in removed.items():
        rows = records[records["canonical_item_id"] == item]
        if set(rows["company"]) != {"acquirer", "target"}:
            continue
        cards = []
        for company in ("acquirer", "target"):
            row = rows[rows["company"] == company].sort_values("spend", ascending=False).iloc[0]
            text = _clean_text(row["description"])
            card = _record_card(priced, row["item_record_id"], text) if text else None
            if card is None or len(text) > MAX_DESCRIPTION:
                break
            card["entity"] = entities.get(card["vendor_key"])
            cards.append(card)
        if len(cards) != 2 or cards[0]["uom"] == cards[1]["uom"]:
            continue
        high, low = sorted((cards[0]["price"], cards[1]["price"]), reverse=True)
        if low <= 0 or high / low < 5:
            continue
        pair = {"stage": "", "tier": "", "cosine": float("nan"), "evidence": ""}
        example = _pair_example(tuple(cards), pair, "trap")
        for key in ("stage", "tier", "similarity", "evidence"):
            example.pop(key)
        example["removed"] = round(float(amount), 2)
        example["ratio"] = round(high / low, 1)
        return example
    return None


def story_object(results: Path) -> dict[str, Any]:
    """What the two companies buy in common, and three real examples of the matching."""
    import pandas as pd

    item_map = pd.read_parquet(results / "item_map.parquet")
    vendor_map = pd.read_parquet(results / "vendor_map.parquet")
    pairs = pd.read_parquet(results / "item_pairs.parquet")
    priced, _ = _item_records(results)
    entities = dict(zip(vendor_map["vendor_key"], vendor_map["legal_entity_id"], strict=True))
    descriptions = {
        k: t
        for k, v in zip(item_map["item_record_id"], item_map["description"], strict=True)
        if (t := _clean_text(v))
    }

    def count(frame: Any, company: str) -> int:
        return int((frame["company"] == company).sum())

    shared_items = item_map[(item_map["company"] == "acquirer") & item_map["partner_id"].notna()]
    by_company = vendor_map.groupby("company")["legal_entity_id"].apply(set)
    overlap = {
        "items": {
            "a": count(item_map, "acquirer"),
            "b": count(item_map, "target"),
            "both": int(len(shared_items)),
        },
        "vendors": {
            "a": len(by_company.get("acquirer", set())),
            "b": len(by_company.get("target", set())),
            "both": len(by_company.get("acquirer", set()) & by_company.get("target", set())),
        },
    }
    examples = {
        "match": _match_example(pairs, descriptions, priced, entities),
        "lookalike": _lookalike_example(pairs, descriptions, priced, entities),
        "trap": _trap_example(results, priced, item_map, entities),
    }
    return {"overlap": overlap, "examples": examples}


def scorecard_object(scorecard: dict) -> dict:
    """The held-out scorecard, the same for every sample."""
    metrics = {}
    for key, value in scorecard["tool"]["held_out"].items():
        target = scorecard.get("targets", {}).get(key)
        metrics[key] = {
            "tool": value,
            "baseline": scorecard["baseline"]["held_out"][key],
            "target": target["bound"] if target else None,
            "direction": target["direction"] if target else None,
        }
    return {"held_out_seed": scorecard["held_out_seed"], "metrics": metrics}


def data_js_object(samples: list[tuple[dict, dict]], scorecard: dict, root: Path = ROOT) -> dict:
    """``samples`` pairs each manifest row with its ``results.json``."""
    currency = samples[0][1]["meta"].get("currency", "USD")
    rows = []
    for i, (sample, results_json) in enumerate(samples):
        story = story_object(root / sample["results"])
        spend = results_json["meta"]["in_scope_spend"]
        story["overlap"]["spend"] = {"a": spend["acquirer"], "b": spend["target"]}
        rows.append(sample_object(sample, results_json, i == 0, story))
    return {
        "currency": currency,
        "samples": rows,
        "scorecard": scorecard_object(scorecard),
    }


def data_js_text(samples: list[tuple[dict, dict]], scorecard: dict) -> str:
    """The text of ``site/data.js``."""
    body = json.dumps(data_js_object(samples, scorecard), indent=2)
    return f"{DATA_JS_HEADER}const TIEOUT = {body};\n"


def read_samples(manifest: Path, root: Path = ROOT) -> list[tuple[dict, dict]]:
    rows = []
    for sample in load_manifest(manifest):
        path = root / sample["results"] / "results.json"
        rows.append((sample, json.loads(path.read_text(encoding="utf-8"))))
    return rows


def write_site_assets(manifest: Path, scorecard_path: Path, site: Path) -> dict[str, int]:
    """Write every sample's three assets and ``data.js`` under ``site``; returns sizes in bytes."""
    from tieout.export.charts import bridge_png
    from tieout.export.deck import build_deck
    from tieout.export.workbook import build_workbook
    from tieout.results import Results

    builders = {"bridge": bridge_png, "workbook": build_workbook, "deck": build_deck}
    samples = read_samples(manifest)
    sizes: dict[str, int] = {}
    for i, (sample, _) in enumerate(samples):
        results = Results.load(ROOT / sample["results"])
        for key, rel in asset_paths(sample["id"], i == 0).items():
            data = builders[key](results, "clean")
            path = site / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sizes[rel] = len(data)
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    text = data_js_text(samples, scorecard)
    (site / "data.js").write_text(text, encoding="utf-8")
    return sizes | {"data.js": len(text.encode())}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "samples.json")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "data" / "demo" / "scorecard.json")
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args(argv)
    for name, size in write_site_assets(args.manifest, args.scorecard, args.site).items():
        print(f"site/{name}: {size / 1_000_000:.2f} MB")


if __name__ == "__main__":
    main()
