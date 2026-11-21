"""Invented company and manufacturer names (PRD 8.1).

Names are built from syllables and screened against ``denylist.txt`` so no
real supplier appears to have real prices. Screening compares normalised
whole words and the joined stem, so "Grain Ger" cannot slip through as a
spaced-out real name.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np

DENYLIST_PATH = Path(__file__).with_name("denylist.txt")

_ONSETS = (
    "b br c cor d dr f g gr h k l m n p pr r s st t tr v z al bel dal hal kal mar nor ser tal ven"
).split()
_VOWELS = "a e i o u a e o a i".split()
_CODAS = "n r l s x nd rn lt st m v ton dell ford vik ra".split()

# Vendor descriptors by L1 code; first entries are the most common.
DESCRIPTORS: dict[str, tuple[str, ...]] = {
    "L01": ("Metals", "Steel", "Alloys", "Metal Service", "Plastics"),
    "L02": ("Fasteners", "Fastening", "Bolt & Screw", "Hardware"),
    "L03": ("Bearings", "Bearing", "Power Transmission", "Drives"),
    "L04": ("Valves", "Pipe & Supply", "Flow Control", "Fluid Systems"),
    "L05": ("Electric", "Electrical", "Controls", "Automation"),
    "L06": ("Abrasives", "Tools", "Tooling", "Cutting Tools"),
    "L07": ("Safety", "Safety Products", "Protective Wear"),
    "L08": ("Packaging", "Container", "Box", "Pallet"),
    "L09": ("Chemicals", "Lubricants", "Chemical", "Coatings"),
    "L10": ("Supply", "Maintenance Supply", "Facility Services", "Industrial Supply"),
    "L11": ("Logistics", "Freight", "Transport", "Express", "Warehousing"),
    "L12": ("Consulting", "Staffing", "Software", "Technologies", "Partners"),
}
GENERIC_WORDS = ("Industrial", "Industries", "Group", "Supply", "Products", "International")
LEGAL_FORMS: dict[str, tuple[str, ...]] = {
    "US": ("Inc", "LLC", "Corp", "Co", "Company", "Incorporated", "Corporation"),
    "CA": ("Ltd", "Inc", "Limited", "Corp"),
    "DE": ("GmbH", "AG"),
    "FR": ("SA", "SAS"),
    "NL": ("BV", "NV"),
    "IT": ("SRL",),
}
COUNTRY_SUFFIX = {
    "CA": "Canada",
    "DE": "Deutschland",
    "FR": "France",
    "NL": "Nederland",
    "IT": "Italia",
}
# Legal-form variants used for alias noise: same entity, different spelling.
LEGAL_VARIANTS: dict[str, tuple[str, ...]] = {
    "Inc": ("Inc.", ", Inc.", "Incorporated", ""),
    "Incorporated": ("Inc", "Inc.", ""),
    "LLC": ("L.L.C.", ", LLC", ""),
    "Corp": ("Corporation", "Corp.", ""),
    "Corporation": ("Corp", "Corp.", ""),
    "Co": ("Co.", "Company", ""),
    "Company": ("Co", "Co.", ""),
    "Ltd": ("Ltd.", "Limited", ""),
    "Limited": ("Ltd", "Ltd.", ""),
    "GmbH": ("G.m.b.H.", ""),
    "AG": ("",),
    "SA": ("S.A.", ""),
    "SAS": ("S.A.S.", ""),
    "BV": ("B.V.", ""),
    "NV": ("N.V.", ""),
    "SRL": ("S.R.L.", ""),
}
# Abbreviations an ERP clerk uses inside vendor names.
NAME_ABBREVIATIONS = {
    "Fastening": "Fastng",
    "Fasteners": "Fstnrs",
    "Industrial": "Indl",
    "Industries": "Inds",
    "International": "Intl",
    "Supply": "Sup",
    "Bearings": "Brgs",
    "Bearing": "Brg",
    "Electrical": "Elec",
    "Electric": "Elec",
    "Products": "Prods",
    "Manufacturing": "Mfg",
    "Maintenance": "Maint",
    "Logistics": "Logist",
    "Transport": "Transp",
    "Technologies": "Tech",
    "Distribution": "Dist",
    "Chemicals": "Chem",
    "Packaging": "Pkg",
    "Services": "Svcs",
    "Company": "Co",
    "Corporation": "Corp",
    "Automation": "Autom",
    "Controls": "Ctrls",
}
_LEGAL_TOKENS = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "llc",
    "ltd",
    "limited",
    "lp",
    "llp",
    "plc",
    "gmbh",
    "ag",
    "sa",
    "sas",
    "srl",
    "bv",
    "nv",
    "pty",
    "ab",
    "oy",
    "kk",
}


@lru_cache(maxsize=1)
def denylist() -> tuple[str, ...]:
    """Normalised denylisted names, in file order."""
    names = []
    for raw in DENYLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            names.append(normalise_name(line))
    return tuple(names)


@lru_cache(maxsize=1)
def _deny_index() -> tuple[frozenset[str], frozenset[str]]:
    full = frozenset(denylist())
    joined = frozenset(n.replace(" ", "") for n in denylist())
    return full, joined


def normalise_name(name: str) -> str:
    """PRD 4.3 V0 normalisation (without alias and branch splitting)."""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", "", text)
    tokens = text.split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in _LEGAL_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def is_denied(name: str) -> bool:
    """True when ``name`` or its stem contains a denylisted name."""
    norm = normalise_name(name)
    full, joined = _deny_index()
    tokens = norm.split()
    if norm in full or norm.replace(" ", "") in joined:
        return True
    for size in range(1, len(tokens) + 1):
        for start in range(len(tokens) - size + 1):
            window = tokens[start : start + size]
            if " ".join(window) in full or "".join(window) in joined:
                return True
    squashed = norm.replace(" ", "")
    return any(len(d) >= 6 and d in squashed for d in joined)


class NameFactory:
    """Unique, screened, pronounceable stems drawn from one random generator."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self._used: set[str] = set()

    def _syllable(self) -> str:
        rng = self._rng
        part = _ONSETS[rng.integers(len(_ONSETS))] + _VOWELS[rng.integers(len(_VOWELS))]
        if rng.random() < 0.55:
            part += _CODAS[rng.integers(len(_CODAS))]
        return part

    def _candidate(self) -> str:
        syllables = 2 if self._rng.random() < 0.85 else 3
        word = "".join(self._syllable() for _ in range(syllables))
        return word[:1].upper() + word[1:]

    def stem(self) -> str:
        """A new stem of 5-9 letters that is unique and not denylisted."""
        while True:
            word = self._candidate()
            if not 5 <= len(word) <= 9 or word.lower() in self._used:
                continue
            if is_denied(word) or re.search(r"(.)\1\1", word):
                continue
            self._used.add(word.lower())
            return word

    def reserve(self, word: str) -> bool:
        """Claim ``word`` if it is free; used for deliberately similar distractor names."""
        if word.lower() in self._used or is_denied(word):
            return False
        self._used.add(word.lower())
        return True


def typo(text: str, rng: np.random.Generator) -> str:
    """One transposition, dropped letter or doubled letter inside a long word."""
    words = text.split(" ")
    candidates = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
    if not candidates:
        return text
    i = candidates[int(rng.integers(len(candidates)))]
    word = words[i]
    pos = int(rng.integers(1, len(word) - 2))
    kind = int(rng.integers(3))
    if kind == 0:
        word = word[:pos] + word[pos + 1] + word[pos] + word[pos + 2 :]
    elif kind == 1:
        word = word[:pos] + word[pos + 1 :]
    else:
        word = word[:pos] + word[pos] + word[pos:]
    words[i] = word
    return " ".join(words)


def mutate_stem(stem: str, rng: np.random.Generator) -> str:
    """A different, similar-looking stem: one vowel or consonant swapped."""
    vowels = "aeiou"
    positions = [i for i in range(1, len(stem)) if stem[i].lower() in vowels]
    if positions and rng.random() < 0.7:
        i = positions[int(rng.integers(len(positions)))]
        options = [v for v in vowels if v != stem[i].lower()]
        return stem[:i] + options[int(rng.integers(len(options)))] + stem[i + 1 :]
    i = int(rng.integers(1, len(stem)))
    options = [c for c in "bdklmnrstv" if c != stem[i].lower()]
    return stem[:i] + options[int(rng.integers(len(options)))] + stem[i + 1 :]
