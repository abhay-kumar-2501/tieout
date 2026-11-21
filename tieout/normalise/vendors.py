"""V0 vendor-name normalisation (PRD 4.3) and tax ID / country clean-up.

The steps run in the PRD order:

1. Unicode NFKC, case-fold, strip accents.
2. Split "doing business as" names (``dba``, ``d/b/a``, ``t/a``) into aliases.
3. Move trailing branch markers into a separate field.
4. ``&`` -> ``and``, remove punctuation, collapse whitespace, drop a leading "the".
5. Remove legal-form tokens from the end of the name only, repeatedly.

The original name is always kept.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

__all__ = [
    "LEGAL_FORMS",
    "VendorName",
    "normalise_country",
    "normalise_tax_id",
    "normalise_vendor_name",
]

LEGAL_FORMS: frozenset[str] = frozenset(
    "inc incorporated corp corporation co company llc ltd limited lp llp plc "
    "gmbh ag sa sas srl bv nv pty ab oy kk".split()
)

_DBA = re.compile(r"(?<![a-z0-9])(?:d\s*/\s*b\s*/\s*a|d\.\s*b\.\s*a\.?|dba|t\s*/\s*a)(?![a-z0-9])")
_MARKER = r"(?:plant|site|branch|store|dc|whse)"
# Tried in this order, repeatedly, each anchored at the end of the name.
_BRANCH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\s*\(\s*(?P<b>{_MARKER}\s*#?\s*[a-z0-9]+)\s*\)\s*$"),
    re.compile(rf"\s+(?P<b>{_MARKER}\s*#?\s*(?:[a-z0-9]*\d[a-z0-9]*|[a-z]))\s*$"),
    re.compile(r"\s*(?P<b>#\s*\d+)\s*$"),
    re.compile(r"\s[-‐-―]\s*(?P<b>[^\-‐-―#()]*[a-z0-9][^\-‐-―#()]*)$"),
)
_DELETED_PUNCT = re.compile(r"['‘’.]")
_OTHER_PUNCT = re.compile(r"[^\w\s]|_")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class VendorName:
    """A vendor name after V0 normalisation.

    ``name`` is the normalised primary name, ``aliases`` the normalised
    "doing business as" names (excluding ``name``), ``branch`` the branch
    marker text if one was found, and ``original`` the name as received.
    """

    original: str
    name: str
    aliases: tuple[str, ...]
    branch: str | None

    @property
    def names(self) -> tuple[str, ...]:
        """Primary name followed by aliases, without blanks."""
        return tuple(n for n in (self.name, *self.aliases) if n)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return not str(value).strip()


def _fold(text: str) -> str:
    """Step 1: NFKC, case-fold, strip accents."""
    text = unicodedata.normalize("NFKC", text).casefold()
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", stripped)


def _split_dba(text: str) -> list[str]:
    """Step 2: split on doing-business-as markers."""
    return [part.strip() for part in _DBA.split(text)]


def _split_branch(text: str) -> tuple[str, str | None]:
    """Step 3: peel trailing branch markers; never leaves the name empty."""
    parts: list[str] = []
    changed = True
    while changed:
        changed = False
        for pattern in _BRANCH_PATTERNS:
            match = pattern.search(text)
            if match and text[: match.start()].strip():
                parts.insert(0, match.group("b").strip())
                text = text[: match.start()].rstrip()
                changed = True
                break
    branch = _SPACES.sub(" ", " ".join(parts)).strip() if parts else None
    return text, branch or None


def _clean(text: str) -> str:
    """Step 4: ampersand, punctuation, whitespace, leading 'the'."""
    text = text.replace("&", " and ")
    text = _DELETED_PUNCT.sub("", text)
    text = _OTHER_PUNCT.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    if text.startswith("the ") and len(text) > 4:
        text = text[4:]
    return text


def _strip_legal_forms(text: str) -> str:
    """Step 5: drop legal-form tokens from the end only, repeatedly.

    A dangling "and" left by the removal ("smith and co") is dropped too, and
    at least one token is always kept.
    """
    tokens = text.split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_FORMS:
        tokens.pop()
        if len(tokens) > 1 and tokens[-1] == "and":
            tokens.pop()
    return " ".join(tokens)


def normalise_vendor_name(original: object) -> VendorName:
    """Normalise one vendor name (PRD 4.3, V0)."""
    raw = "" if _is_blank(original) else str(original)
    names: list[str] = []
    branch: str | None = None
    for part in _split_dba(_fold(raw)):
        part, part_branch = _split_branch(part)
        branch = branch or part_branch
        name = _strip_legal_forms(_clean(part))
        if name and name not in names:
            names.append(name)
    primary = names[0] if names else ""
    return VendorName(original=raw, name=primary, aliases=tuple(names[1:]), branch=branch)


def normalise_tax_id(value: object) -> str | None:
    """Upper-case alphanumerics only; ``None`` when nothing is left."""
    if _is_blank(value):
        return None
    cleaned = "".join(c for c in _fold(str(value)) if c.isalnum()).upper()
    return cleaned or None


def normalise_country(value: object) -> str | None:
    """Upper-cased ISO alpha-2 code; anything that is not two letters is blank."""
    if _is_blank(value):
        return None
    code = str(value).strip().upper()
    return code if len(code) == 2 and code.isascii() and code.isalpha() else None
