"""Noise models (PRD 8.2 step 3), each applied at a documented rate.

Vendor names: aliases and legal-form variants, typos, truncation. Tax IDs:
missing values and formatting. Item text noise lives in ``render`` because it
is part of each ERP style.
"""

from __future__ import annotations

import re

import numpy as np

from synthetic.names import LEGAL_VARIANTS, NAME_ABBREVIATIONS, typo

ALIAS_KINDS = ("legal_form", "abbreviation", "ampersand", "article", "branch")
BRANCH_CITIES = ("Chicago", "Houston", "Toronto", "Atlanta", "Denver", "Phoenix", "Memphis", "Reno")


def legal_form_variant(name: str, rng: np.random.Generator) -> str:
    """Respell or drop the trailing legal form ("Inc" -> "Incorporated")."""
    head, _, last = name.rpartition(" ")
    options = LEGAL_VARIANTS.get(last)
    if not head or not options:
        return name
    variant = options[int(rng.integers(len(options)))]
    if not variant:
        return head
    return head + variant if variant.startswith(",") else f"{head} {variant}"


def abbreviate_name(name: str, rng: np.random.Generator) -> str:
    """Clerk abbreviations inside a name ("Fastening" -> "Fastng")."""
    words = name.split(" ")
    hits = [i for i, w in enumerate(words) if w in NAME_ABBREVIATIONS]
    if not hits:
        return legal_form_variant(name, rng)
    for i in hits:
        if rng.random() < 0.8:
            words[i] = NAME_ABBREVIATIONS[words[i]]
    return " ".join(words)


def alias_variant(name: str, rng: np.random.Generator) -> tuple[str, str]:
    """One alias or legal-form variant; returns (new name, kind)."""
    roll = rng.random()
    if roll < 0.45:
        return legal_form_variant(name, rng), "legal_form"
    if roll < 0.70:
        return abbreviate_name(name, rng), "abbreviation"
    if roll < 0.80 and " & " in name:
        return name.replace(" & ", " and "), "ampersand"
    if roll < 0.88:
        return f"The {name}", "article"
    city = BRANCH_CITIES[int(rng.integers(len(BRANCH_CITIES)))]
    marker = (f"- {city}", f"#{int(rng.integers(2, 60))}", f"(Plant {int(rng.integers(1, 9))})")
    return f"{name} {marker[int(rng.integers(3))]}", "branch"


def with_typo(name: str, rng: np.random.Generator) -> str:
    return typo(name, rng)


def truncate(text: str, length: int) -> str:
    return text[:length].rstrip()


def upper_style(name: str) -> str:
    """Target ERP: upper case, punctuation other than & and # removed."""
    text = re.sub(r"[^\w\s&#()\-]", "", name.upper())
    return " ".join(text.split())


def render_tax_id(tax_id: str, style: str) -> str:
    """Acquirer keeps the issuer's punctuation; the target stores alphanumerics only."""
    return tax_id if style == "A" else re.sub(r"[^0-9A-Z]", "", tax_id.upper())
