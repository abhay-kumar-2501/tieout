"""Vendor matching runs on ~2,500 records in a few seconds (blocking + cdist)."""

import random
import time

import pandas as pd

from tieout.match.vendors import match_vendors

SYLLABLES = "ka lo mi ta ren vor sel dan bri qua zel mon tor fen gal hus pra lin dre os".split()
WORDS = ["precision", "machining", "marine", "valve", "fabrication", "tools", "logistics"]
WORDS += ["industrial", "supply", "plastics", "electric", "works", "engineering", "group"]
FORMS = ["Inc", "LLC", "Corp", "Ltd", "Co", ""]


def _names(n: int, seed: int = 7) -> list[str]:
    rng = random.Random(seed)
    names = []
    for _ in range(n):
        stem = "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 3))).title()
        words = " ".join(rng.sample(WORDS, rng.randint(1, 2))).title()
        names.append(f"{stem} {words} {rng.choice(FORMS)}".strip())
    return names


def _noisy(name: str, rng: random.Random) -> str:
    if rng.random() < 0.08 and len(name) > 6:
        i = rng.randrange(1, len(name) - 1)
        name = name[:i] + name[i + 1 :]
    return name[:30]


def test_2500_records_match_in_a_few_seconds() -> None:
    rng = random.Random(11)
    acquirer = _names(1300, seed=1)
    target = [_noisy(n, rng) for n in acquirer[:500]] + _names(700, seed=2)
    rows = [
        {
            "vendor_key": f"{company}:V{i:05d}",
            "company": company,
            "vendor_id": f"V{i:05d}",
            "vendor_name": name,
            "vendor_tax_id": f"T{i}" if rng.random() < 0.3 else None,
            "vendor_country": "US",
            "spend": 1.0,
        }
        for company, names in (("acquirer", acquirer), ("target", target))
        for i, name in enumerate(names)
    ]
    records = pd.DataFrame(rows)
    start = time.perf_counter()
    result = match_vendors(records)
    elapsed = time.perf_counter() - start
    assert len(result.vendor_map) == 2500
    assert elapsed < 5.0, f"vendor matching took {elapsed:.2f}s"
    start = time.perf_counter()
    match_vendors(records, cached_pairs=result.pairs)
    assert time.perf_counter() - start < 2.0
