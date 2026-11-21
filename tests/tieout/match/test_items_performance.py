"""Item matching at demo scale: ~5,500 x 3,500 records over 60 L2s in well under 20 s.

The generator writes every item in two ERP styles (abbreviation habits and token
order differ) and plants near-identical items differing in one attribute, so it
also checks that the guards hold at scale.
"""

from __future__ import annotations

import random
import time
import zlib
from collections.abc import Callable

import pandas as pd

from tieout.match.items import ITEM_RECORD_COLUMNS, match_items
from tieout.reference import load_taxonomy

Attrs = dict[str, str]
Render = Callable[[Attrs, int], str]


def _fasteners(rng: random.Random) -> Attrs:
    return {
        "d": rng.choice(["M5", "M6", "M8", "M10", "M12", "M16"]),
        "len": str(rng.choice([10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 100])),
        "grade": rng.choice(["8.8", "10.9", "12.9"]),
        "finish": rng.choice(["ZP", "HDG", "PLAIN", "BLK OX"]),
        "head": rng.choice(["HHCS", "SHCS", "BHCS", "FHCS"]),
    }


def _render_fasteners(a: Attrs, style: int) -> str:
    long_head = {
        "HHCS": "HEX HEAD CAP SCREW",
        "SHCS": "SOCKET HEAD CAP SCREW",
        "BHCS": "BUTTON HEAD CAP SCREW",
        "FHCS": "FLAT HEAD CAP SCREW",
    }[a["head"]]
    long_finish = {
        "ZP": "ZINC PLATED",
        "HDG": "HOT DIP GALV",
        "PLAIN": "PLAIN",
        "BLK OX": "BLACK OXIDE",
    }
    if style == 0:
        return f"{a['head']} {a['d']}X{a['len']} {a['grade']} {a['finish']}"
    return f"{long_head} {a['d']} x {a['len']}MM CL {a['grade']} {long_finish[a['finish']]}"


def _bearings(rng: random.Random) -> Attrs:
    return {
        "base": rng.choice(
            ["6000", "6001", "6201", "6202", "6203", "6204", "6205", "6206", "6304"]
        ),
        "seal": rng.choice(["2RS", "ZZ", ""]),
        "c": rng.choice(["", "C3"]),
    }


def _render_bearings(a: Attrs, style: int) -> str:
    if style == 0:
        suffix = "".join(f"-{p}" for p in (a["seal"], a["c"]) if p)
        return f"BRG BALL {a['base']}{suffix}"
    seal = {"2RS": "2RS1", "ZZ": "2Z", "": ""}[a["seal"]]
    tail = "/".join(p for p in (seal, a["c"]) if p)
    return f"{a['base']}{'-' + tail if tail else ''} DEEP GROOVE BALL BEARING"


def _pvf(rng: random.Random) -> Attrs:
    return {
        "size": rng.choice(["1/4", "1/2", "3/4", "1", "1-1/2", "2", "3"]),
        "cls": rng.choice(["150", "300", "600", "3000"]),
        "mat": rng.choice(["SS", "BRASS", "CS"]),
        "end": rng.choice(["FNPT", "SW", "BW"]),
    }


def _render_pvf(a: Attrs, style: int) -> str:
    if style == 0:
        return f"BALL VLV {a['size']}IN {a['end']} {a['mat']} {a['cls']}#"
    end = {"FNPT": "FEMALE NPT", "SW": "SOCKET WELD", "BW": "BUTT WELD"}[a["end"]]
    mat = {"SS": "STAINLESS", "BRASS": "BRASS", "CS": "CARBON STEEL"}[a["mat"]]
    return f'{mat} BALL VALVE {a["size"]}" CLASS {a["cls"]} {end}'


def _electrical(rng: random.Random) -> Attrs:
    return {
        "p": rng.choice(["1", "2", "3"]),
        "a": rng.choice(["15", "20", "30", "40", "60", "100"]),
        "v": rng.choice(["120", "240", "480", "600"]),
    }


def _render_electrical(a: Attrs, style: int) -> str:
    if style == 0:
        return f"BRKR {a['p']}P {a['a']}A {a['v']}V"
    return f"CIRCUIT BREAKER {a['v']} VOLT {a['p']} POLE {a['a']} AMP"


def _ppe(rng: random.Random) -> Attrs:
    return {
        "m": rng.choice(["NITRILE", "LATEX", "VINYL"]),
        "s": rng.choice(["S", "M", "L", "XL"]),
        "mil": rng.choice(["4", "5", "6", "8"]),
    }


def _render_ppe(a: Attrs, style: int) -> str:
    size = {"S": "SMALL", "M": "MEDIUM", "L": "LARGE", "XL": "X-LARGE"}[a["s"]]
    if style == 0:
        short = {"NITRILE": "NTR", "LATEX": "LTX", "VINYL": "VINYL"}[a["m"]]
        return f"GLV {short} DISP {a['mil']}MIL {a['s']} BX/100"
    return f"{a['m']} DISPOSABLE GLOVES {size} {a['mil']} MIL 100/BX"


def _abrasives(rng: random.Random) -> Attrs:
    return {
        "d": rng.choice(["4-1/2", "5", "6", "7"]),
        "grit": rng.choice(["36", "40", "60", "80", "120"]),
        "bore": rng.choice(["7/8", "5/8-11"]),
        "t": rng.choice(["27", "29"]),
    }


def _render_abrasives(a: Attrs, style: int) -> str:
    if style == 0:
        return f"FLAP DISC {a['d']} X {a['bore']} {a['grit']} GRIT ZIRC T{a['t']}"
    return f'ZIRCONIA FLAP DISC TYPE {a["t"]} {a["d"]}" {a["grit"]}G {a["bore"]} ARBOR'


def _generic(rng: random.Random) -> Attrs:
    return {
        "w": str(rng.choice([12, 18, 20, 24, 30])),
        "l": str(rng.choice([500, 1000, 1500, 2000])),
        "ga": str(rng.choice([60, 70, 80, 90, 100])),
        "word": rng.choice(["CLEAR", "BLACK", "BLUE", "CAST", "BLOWN"]),
    }


def _render_generic(a: Attrs, style: int) -> str:
    if style == 0:
        return f"STRETCH FILM {a['word']} {a['w']}IN X {a['l']}FT {a['ga']}GA"
    return f"FILM STRETCH {a['ga']} GA {a['w']}\" X {a['l']}' {a['word']} CS/4"


FAMILIES: dict[str, tuple[Callable[[random.Random], Attrs], Render]] = {
    "fasteners": (_fasteners, _render_fasteners),
    "bearings": (_bearings, _render_bearings),
    "pvf": (_pvf, _render_pvf),
    "electrical": (_electrical, _render_electrical),
    "ppe": (_ppe, _render_ppe),
    "abrasives": (_abrasives, _render_abrasives),
    "generic": (_generic, _render_generic),
}


def generate(n_acq: int = 5500, n_tgt: int = 3500, seed: int = 11) -> pd.DataFrame:
    rng = random.Random(seed)
    taxonomy = load_taxonomy()
    rows: list[dict] = []
    per_acq, per_tgt = -(-n_acq // 60), -(-n_tgt // 60)
    for l2_code, family in taxonomy[["l2_code", "family"]].itertuples(index=False):
        make, render = FAMILIES[family]
        seen: set[tuple[str, ...]] = set()
        items: list[Attrs] = []
        while len(items) < per_acq + per_tgt:
            # A series number keeps items distinct where attribute combinations run out.
            attrs = make(rng) | {"series": str(rng.randint(1, 60))}
            key = tuple(sorted(attrs.items()))
            if key not in seen:
                seen.add(key)
                items.append(attrs)
        shared = items[: per_tgt // 2]
        acq_items = shared + items[per_tgt // 2 : per_acq]
        tgt_items = shared + items[per_acq : per_acq + per_tgt - len(shared)]
        for company, chosen, style in (("acquirer", acq_items, 0), ("target", tgt_items, 1)):
            for k, attrs in enumerate(chosen):
                truth = "|".join(f"{key}={value}" for key, value in sorted(attrs.items()))
                use_mpn = k < len(shared) and k % 5 < 3
                rows.append(
                    {
                        "item_record_id": f"{company}:{l2_code}-{k:04d}",
                        "company": company,
                        "item_key": f"{l2_code}-{k:04d}",
                        "item_code": f"{l2_code}-{k:04d}",
                        "mpn": f"MP{zlib.crc32(truth.encode()):010d}" if use_mpn else None,
                        "manufacturer": "ACME",
                        "description": render(attrs, style)
                        + (
                            f" SER {attrs['series']}"
                            if style == 0
                            else f" SERIES {attrs['series']}"
                        ),
                        "l2_code": l2_code,
                        "family": family,
                        "spend": 1.0,
                        "truth": f"{l2_code}:{truth}",
                    }
                )
    return pd.DataFrame(rows)


def test_demo_scale_runs_well_under_twenty_seconds() -> None:
    data = generate()
    assert len(data) >= 9000
    records = data[ITEM_RECORD_COLUMNS]

    start = time.perf_counter()
    result = match_items(records)
    elapsed = time.perf_counter() - start
    assert elapsed < 20.0, f"item matching took {elapsed:.1f}s"

    start = time.perf_counter()
    match_items(records, cached_pairs=result.pairs)
    assert time.perf_counter() - start < 5.0

    # Guards hold at scale: automatic pairs join records describing the same item.
    truth = dict(zip(data["item_record_id"], data["truth"], strict=True))
    matched = result.pairs[result.pairs["tier"].isin(["A", "B"])]
    correct = sum(truth[a] == truth[b] for a, b in zip(matched.key_a, matched.key_b, strict=True))
    assert len(matched) > 0
    assert correct / len(matched) >= 0.99
