"""Unexplained differences between two item descriptions (an I3 automatic-match guard).

Two descriptions of the same good may differ by *omission* (one clerk drops the
colour, or the field cuts the text short) and by *rendering* (abbreviations,
word order, separators). When each side states something the other side does
not, and no rendering rule explains it, the two most likely name different
goods: ``DRILL BIT HSS TIN`` against ``DRILL BIT HSS BLACK OXIDE``, ``6 HOLE``
against ``NO HOLE``. Such a pair is never matched automatically (PRD 4.1:
precision over recall); it can still go to review.

Both descriptions are I0-normalised. Each token is read as parts:

* a *code* starts with letters and contains a digit (``CL8``, ``T27``,
  ``E71T``, ``M10``);
* a *number* is canonical (``1/2`` and ``0.5`` agree; ``300#`` is 300);
* a *word* is a run of letters, possibly joined by slashes (``HOLE``,
  ``AL/SS``).

So ``6805-2Z`` and ``6805 2Z`` read alike, and ``100R17`` is 100, R, 17.

A part on one side is *explained* by the other side when the other side has

* the same part (numbers count with multiplicity: ``5IN ... 5 HOLE`` states 5
  twice);
* for a code, a number equal to its digits (``CL300`` / ``300#``);
* for a plain word, a word it is a prefix of, or that is a prefix of it
  (``HYD`` / ``HYDRAULIC``), or a word or run of consecutive words it
  abbreviates (``SNDG`` / ``SANDING``, ``YZN`` / ``YELLOW ZINC``; see
  :func:`is_abbreviation`).

The last token of a description that is a prefix of a token on the other side
is a field cut short by its length limit and is ignored.
"""

from __future__ import annotations

import re
from collections import Counter

from tieout.match.attributes import fmt, to_float
from tieout.normalise.spelling import is_abbreviation

__all__ = ["describe", "unexplained_tokens"]

_EDGE_PUNCT = "-/.#"
_PART = re.compile(
    r"(?P<code>[A-Z]+\d[A-Z0-9.]*)"
    r"|(?P<number>\d+-\d+/\d+|\d+/\d+|\d*\.\d+|\d+)"
    r"|(?P<word>[A-Z]+(?:/[A-Z]+)*)"
)


def _raw_tokens(text: str) -> list[str]:
    return [t for t in (tok.strip(_EDGE_PUNCT) for tok in text.split()) if t]


def _drop_truncated_tail(tokens: list[str], other: list[str]) -> list[str]:
    if not tokens:
        return tokens
    last = tokens[-1]
    if last not in other and any(t.startswith(last) for t in other):
        return tokens[:-1]
    return tokens


class _Parts:
    """Codes, numbers (with multiplicity) and words (in order) of one description."""

    def __init__(self, tokens: list[str]) -> None:
        self.codes: set[str] = set()
        self.numbers: Counter[str] = Counter()
        self.words: list[str] = []
        for token in tokens:
            for m in _PART.finditer(token):
                if m.group("code"):
                    self.codes.add(m.group("code"))
                elif m.group("number"):
                    self.numbers[fmt(to_float(m.group("number")))] += 1
                elif m.group("word") not in self.words:
                    self.words.append(m.group("word"))


def _word_explained(word: str, candidates: list[str]) -> bool:
    if word in candidates:
        return True
    if not word.isalpha():
        return False
    letters = [c for c in candidates if c.isalpha()]
    for other in letters:
        if other.startswith(word) or word.startswith(other):
            return True
        if is_abbreviation(word, other) or is_abbreviation(other, word):
            return True
    for start in range(len(letters)):
        for end in range(start + 2, len(letters) + 1):
            if is_abbreviation(word, "".join(letters[start:end])):
                return True
    return False


def _code_explained(code: str, other: _Parts) -> bool:
    if code in other.codes:
        return True
    digits = re.sub(r"^[A-Z]+", "", code)
    return digits.replace(".", "").isdigit() and other.numbers[fmt(to_float(digits))] > 0


def _unexplained(mine: _Parts, other: _Parts) -> set[str]:
    out = {c for c in mine.codes if not _code_explained(c, other)}
    out |= set(mine.numbers - other.numbers)
    left = [w for w in mine.words if w not in other.words]
    remaining = [w for w in other.words if w not in mine.words]
    out |= {w for w in left if not _word_explained(w, remaining)}
    return out


def unexplained_tokens(text_a: str, text_b: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Parts of each normalised description that the other does not explain.

    Returns ``(only_a, only_b)``, each sorted. The pair has a two-sided
    difference when both are non-empty.
    """
    raw_a, raw_b = _raw_tokens(text_a), _raw_tokens(text_b)
    raw_a, raw_b = _drop_truncated_tail(raw_a, raw_b), _drop_truncated_tail(raw_b, raw_a)
    parts_a, parts_b = _Parts(raw_a), _Parts(raw_b)
    only_a = _unexplained(parts_a, parts_b)
    only_b = _unexplained(parts_b, parts_a)
    return tuple(sorted(only_a)), tuple(sorted(only_b))


def describe(only_a: tuple[str, ...], only_b: tuple[str, ...]) -> str:
    """``TIN vs BLACK OXIDE``-style text for evidence."""
    return f"{' '.join(only_a)} vs {' '.join(only_b)}"
