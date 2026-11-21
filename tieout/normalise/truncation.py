"""Detect text fields that a source system cut at a fixed length.

ERP fields have length limits (PRD 8.2 lists names "cut at a fixed field
length"). A cut field piles values up at the limit, while uncut text spreads
out, so a company's texts were cut when the longest length is shared by at
least ``MIN_SHARE`` of them (and at least ``MIN_COUNT``). The last word of a
value at that length may be incomplete.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["MIN_COUNT", "MIN_SHARE", "cut_length"]

MIN_SHARE = 0.01
MIN_COUNT = 3


def cut_length(values: Iterable[object]) -> int | None:
    """The length at which ``values`` were cut, or ``None`` when they were not.

    Values are compared after trimming; blanks are ignored.
    """
    lengths = [len(str(v).strip()) for v in values if v is not None and str(v).strip()]
    if not lengths:
        return None
    longest = max(lengths)
    at_limit = lengths.count(longest)
    return longest if at_limit >= max(MIN_COUNT, MIN_SHARE * len(lengths)) else None
