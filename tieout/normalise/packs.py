"""Pack quantities stated in item descriptions (PRD 3.5).

Only the five documented patterns are recognised; the first pattern that
matches with a quantity from 2 to 10,000 wins. Nothing else is parsed.
"""

from __future__ import annotations

import re

MIN_PACK_QTY = 2
MAX_PACK_QTY = 10_000

_N = r"(?P<n>\d+)"
_START = r"(?<![A-Z0-9])"
_END = r"(?![A-Z0-9])"

_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(_START + body + _END, re.IGNORECASE)
    for body in (
        rf"(?:BOX|BX|CASE|CS|PACK|PK|PKG|BAG|BG|ROLL|RL)\s*(?:OF\s*)?{_N}",
        rf"{_N}\s*/\s*(?:BX|CS|PK|BG|RL)",
        rf"(?:BX|CS|PK|BG|RL)\s*/\s*{_N}",
        rf"{_N}\s*(?:PER|PR)\s*(?:BOX|CASE|PACK|BAG)",
        rf"{_N}\s*(?:PC|PCS|EA|CT)\s*/?\s*(?:BX|CS|PK|BG)",
    )
)


def _find(description: str) -> re.Match[str] | None:
    for pattern in _PATTERNS:
        for match in pattern.finditer(description):
            if MIN_PACK_QTY <= int(match.group("n")) <= MAX_PACK_QTY:
                return match
    return None


def parse_pack_qty(description: str | None) -> int | None:
    """Return the pack quantity stated in ``description``, or ``None``."""
    if not description:
        return None
    match = _find(description)
    return int(match.group("n")) if match else None


def strip_pack_tokens(description: str | None) -> str:
    """Remove the pack-quantity phrase so it is not mistaken for an item attribute."""
    if not description:
        return ""
    match = _find(description)
    if match is None:
        return description
    remainder = description[: match.start()] + " " + description[match.end() :]
    return " ".join(remainder.split())
