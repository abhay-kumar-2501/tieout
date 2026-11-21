"""Item description, part-number and manufacturer normalisation (PRD 4.4, I0 and I1).

* :func:`normalise_description` is step I0: upper-case, standardise inch and foot
  marks and dimension separators, then expand whole-token abbreviations.
* :func:`normalise_mpn` / :func:`mpn_key` implement the I1 MPN rule.
* :func:`normalise_manufacturer` / :func:`manufacturers_compatible` implement the
  I1 manufacturer rule (V0 normalisation, then equality, blank, or
  ``token_sort_ratio`` of at least 90).
* :func:`extract_mpn_like_tokens` finds part-number-like tokens in a description;
  they are only ever a candidate signal for I3.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from functools import lru_cache

from rapidfuzz import fuzz

from tieout.normalise.spelling import is_abbreviation
from tieout.normalise.vendors import normalise_name
from tieout.reference import load_abbreviations

__all__ = [
    "MANUFACTURER_MIN_RATIO",
    "MPN_MIN_LENGTH",
    "extract_mpn_like_tokens",
    "is_dimension_token",
    "is_valid_mpn",
    "item_key",
    "manufacturers_compatible",
    "mpn_key",
    "normalise_description",
    "normalise_manufacturer",
    "normalise_mpn",
]

MPN_MIN_LENGTH = 5
MANUFACTURER_MIN_RATIO = 90.0

# --------------------------------------------------------------------------- I0

# Units that are glued to the number in front of them ("40 MM" -> "40MM").
_JOIN_UNITS = (
    "MM|CM|IN|FT|YD|VAC|VDC|V|AMPS|AMP|A|HP|KW|W|PSI|LBS|LB|OZ|GA|AWG|GRIT|MIL|ML|GAL|KG|DEG|RPM"
)
_INCH_MARK = re.compile(r"(?<=[\d/.])\s*(?:\"|''|”|″)")
_FOOT_MARK = re.compile(r"(?<=\d)\s*(?:'|’|′)(?!')")
_UNIT_SPACE = re.compile(rf"(?<=\d)\s+(?=(?:{_JOIN_UNITS})(?![A-Z0-9]))")
# "8 x 40", "4-1/2IN x 1/4IN", "100 * 6" -> "8X40", "4-1/2INX1/4IN", "100X6".
# A separator attached on the left but not the right ("NEMA 4X 24") is not joined.
_TIMES = re.compile(r"(?<=\d)((?:IN|MM|CM|FT)?)(?:\s+[X×\*]\s*|[X×\*])(?=\.?\d|#\d)")
# Metric thread with a dash before an integer length: "M8-40" -> "M8X40".
_METRIC_DASH = re.compile(r"(?<![A-Z0-9])M(\d+(?:\.\d+)?)\s*-\s*(\d+)(?![\d./])")
# A mixed number written with a space ("1 1/2") becomes "1-1/2" before anything
# else, so that later steps never read two neighbouring fields as one number.
_MIXED_NUMBER = re.compile(r"(?<![\w#./-])(\d{1,2}) (\d+/\d+)(?![\d/])")
# Field separators: "BELT,TIMING,920" reads as the words "BELT TIMING 920". Commas are
# never decimal or thousands marks in descriptions (a field-per-comma style puts
# numbers side by side: "BELT,TIMING,2560,850MM"). They are replaced after units
# and dimensions are joined, so nothing is joined across a comma.
_LIST_SEPARATOR = re.compile(r"[,;]")
_WORD = re.compile(r"(?<![A-Z0-9])[A-Z]+(?![A-Z0-9])")
_SPACES = re.compile(r"\s+")


@lru_cache(maxsize=1)
def _default_abbreviations() -> dict[str, str]:
    return {k.strip().upper(): v.strip().upper() for k, v in load_abbreviations().items()}


def normalise_description(text: str | None, abbreviations: Mapping[str, str] | None = None) -> str:
    """Return the I0-normalised description.

    Upper-cases, writes mixed numbers with a hyphen (``1 1/2`` -> ``1-1/2``),
    turns inch and foot marks into ``IN`` / ``FT``, standardises dimension
    separators (``M8 x 40``, ``M8-40`` -> ``M8X40``), glues units to their
    numbers, reads commas and semicolons as word breaks, expands whole-token
    abbreviations and collapses whitespace.
    """
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).upper()
    s = _MIXED_NUMBER.sub(r"\1-\2", s)
    s = _INCH_MARK.sub("IN", s)
    s = _FOOT_MARK.sub("FT", s)
    s = _UNIT_SPACE.sub("", s)
    s = _METRIC_DASH.sub(r"M\1X\2", s)
    s = _TIMES.sub(r"\1X", s)
    s = _LIST_SEPARATOR.sub(" ", s)
    abbr = _default_abbreviations() if abbreviations is None else abbreviations
    s = _WORD.sub(lambda m: abbr.get(m.group(0), m.group(0)), s)
    return _SPACES.sub(" ", s).strip()


# --------------------------------------------------------------------------- MPN


def normalise_mpn(value: object) -> str | None:
    """Alphanumerics only, upper-case; ``None`` when nothing is left."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    norm = re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", str(value)).upper())
    return norm or None


def is_valid_mpn(mpn_norm: str | None) -> bool:
    """At least five characters, including a digit (PRD 4.4 I1)."""
    return (
        mpn_norm is not None
        and len(mpn_norm) >= MPN_MIN_LENGTH
        and any(ch.isdigit() for ch in mpn_norm)
    )


def mpn_key(value: object) -> str | None:
    """The normalised MPN when it is valid for I1, else ``None``."""
    norm = normalise_mpn(value)
    return norm if is_valid_mpn(norm) else None


# --------------------------------------------------------------- manufacturer


def normalise_manufacturer(value: object) -> str:
    """V0 normalisation of a manufacturer name (PRD 4.3); ``""`` when blank.

    The vendor V0 steps without aliases and branches: NFKC, case-fold, strip
    accents, ``&`` -> ``and``, remove punctuation, collapse whitespace, drop a
    leading "the", remove trailing legal forms.
    """
    return normalise_name(value)


def _is_short_form(short: list[str], long: list[str]) -> bool:
    """``short`` is ``long`` with later words abbreviated or dropped.

    The first words are equal, and each later word of ``short`` is equal to,
    the start of, or an abbreviation of the word in the same place in ``long``
    (``PRESTVA`` / ``Prestva Bearing``, ``ALESTUV ELEC`` / ``Alestuv Electric``).
    """
    if not short or len(short) > len(long) or short[0] != long[0]:
        return False
    return all(
        s == w or w.startswith(s) or is_abbreviation(s, w)
        for s, w in zip(short[1:], long[1:], strict=False)
    )


def manufacturers_compatible(a: object, b: object) -> bool:
    """Equal after V0, either blank, ``token_sort_ratio`` >= 90, or a short form.

    The short-form case (:func:`_is_short_form`) goes beyond PRD 4.4: purchasing
    systems often keep only a manufacturer's leading word or an abbreviation.
    """
    na, nb = normalise_manufacturer(a), normalise_manufacturer(b)
    if not na or not nb or na == nb:
        return True
    if fuzz.token_sort_ratio(na, nb) >= MANUFACTURER_MIN_RATIO:
        return True
    ta, tb = na.split(), nb.split()
    return _is_short_form(ta, tb) or _is_short_form(tb, ta)


def item_key(item_code: object, mpn: object, manufacturer: object) -> str | None:
    """ARCHITECTURE.md ``item_key``: the item code, else ``MPN:{mpn}|{manufacturer}``."""
    if item_code is not None and not (isinstance(item_code, float) and item_code != item_code):
        code = str(item_code).strip()
        if code:
            return code
    norm = normalise_mpn(mpn)
    if norm is None:
        return None
    return f"MPN:{norm}|{normalise_manufacturer(manufacturer)}"


# ------------------------------------------------------- MPN-like description tokens

_MPN_LIKE = re.compile(r"(?<![A-Z0-9])[A-Z0-9][A-Z0-9\-/\.]{4,}")
_NUM = r"(?:\d+-\d+/\d+|\d+/\d+|\d*\.\d+|\d+)"
_DIM_UNIT = (
    r"(?:MM|CM|IN|FT|M|V|VAC|VDC|A|AMP|AMPS|HP|KW|W|PSI|LB|LBS|OZ|GA|AWG|GRIT|MIL|ML|GAL|"
    r"KG|DEG|RPM|PH|P|T|TPI|FL|G|L|K|NM)"
)
_DIMENSION = re.compile(
    rf"^(?:M|#)?{_NUM}{_DIM_UNIT}?(?:[X\-](?:M|#)?{_NUM}{_DIM_UNIT}?)*$",
)


def is_dimension_token(token: str) -> bool:
    """True for sizes and measurements such as ``M8X40``, ``1/4-20X1``, ``120VAC``."""
    return bool(_DIMENSION.match(token.upper().strip(".-/")))


def extract_mpn_like_tokens(description: str | None) -> list[str]:
    """MPN-like tokens of a description, normalised, sorted and unique.

    A token matches ``[A-Z0-9][A-Z0-9\\-/\\.]{4,}``, contains a letter and a
    digit, and is not a dimension. These are I3 candidate evidence only.
    """
    if not description:
        return []
    text = unicodedata.normalize("NFKC", str(description)).upper()
    found: set[str] = set()
    for match in _MPN_LIKE.finditer(text):
        token = match.group(0).rstrip("-/.")
        if len(token) < MPN_MIN_LENGTH:
            continue
        if not (any(c.isalpha() for c in token) and any(c.isdigit() for c in token)):
            continue
        if is_dimension_token(token):
            continue
        norm = normalise_mpn(token)
        if is_valid_mpn(norm):
            found.add(norm)  # type: ignore[arg-type]
    return sorted(found)
