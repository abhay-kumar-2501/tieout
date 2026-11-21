"""Spelling relations between two words: typing slips and abbreviations.

Both are used to read the same word through the noise of hand-typed master
data, never to relate two different words.
"""

from __future__ import annotations

from rapidfuzz.distance import OSA, Levenshtein

__all__ = ["is_abbreviation", "is_typing_slip"]

_VOWELS = frozenset("AEIOUaeiou")


def is_typing_slip(a: str, b: str) -> bool:
    """One typing slip: a doubled, dropped or inserted letter, or two neighbours swapped.

    A substituted letter is not a slip: it makes a different word (``gilthali``
    / ``gilthalt``).
    """
    if abs(len(a) - len(b)) == 1:
        return Levenshtein.distance(a, b) == 1
    return len(a) == len(b) and a != b and sorted(a) == sorted(b) and OSA.distance(a, b) == 1


def is_abbreviation(short: str, long: str) -> bool:
    """``short`` abbreviates ``long``.

    It keeps the first letter and a subsequence of the other letters, and it
    either drops at least two letters or has no vowel after the first letter
    (``DSC`` / ``DISC``, ``ROLR`` / ``ROLLER``, but not ``SOOW`` / ``SEOOW``,
    which are different cable types).
    """
    if not short or len(short) >= len(long) or short[0] != long[0]:
        return False
    if len(long) - len(short) < 2 and _VOWELS & set(short[1:]):
        return False
    rest = iter(long[1:])
    return all(ch in rest for ch in short[1:])
