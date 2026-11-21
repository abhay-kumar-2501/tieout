"""Prioritisation: complexity score and wave (PRD 5.7).

Five factors, each scored on the integers 1 to 5 from the PRD's second table,
are averaged with the weights of its first table. The wave is the first rule
that matches: available month above 12 is wave 3; lever-1 ``same_vendor`` or
lever 3 with available month at most 3 and complexity at most 2.5 is wave 1;
everything else is wave 2.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "CHANGE_SCORES",
    "FACTOR_COLUMNS",
    "WEIGHTS",
    "complexity",
    "contract_score",
    "criticality_score",
    "match_score",
    "prioritise",
    "sites_score",
    "wave",
]

WEIGHTS = {"contract": 0.30, "change": 0.25, "criticality": 0.20, "sites": 0.10, "match": 0.15}
FACTOR_COLUMNS = [f"score_{name}" for name in WEIGHTS]
CHANGE_SCORES = {
    "same_vendor": 1,
    "terms": 2,
    "existing_vendor": 3,
    "re_tender": 4,
    "new_vendor": 5,
}
CRITICALITY_SCORES = {"non_critical": 1, "standard": 3, "critical": 5}
WAVE1_MAX_AVAILABLE = 3
WAVE1_MAX_COMPLEXITY = 2.5
WAVE3_MIN_AVAILABLE = 12


def contract_score(available_month: np.ndarray) -> np.ndarray:
    """0 (or no contract data) -> 1, 1-6 -> 2, 7-12 -> 3, 13-24 -> 4, over 24 -> 5."""
    return np.searchsorted([0, 6, 12, 24], np.asarray(available_month), side="left") + 1


def sites_score(sites: np.ndarray) -> np.ndarray:
    """1 -> 1, 2 -> 2, 3-4 -> 3, 5-9 -> 4, 10 or more -> 5."""
    return np.searchsorted([1, 2, 4, 9], np.asarray(sites), side="left") + 1


def criticality_score(criticality: np.ndarray) -> np.ndarray:
    """Non-critical 1, standard 3, critical 5."""
    return np.array([CRITICALITY_SCORES[c] for c in criticality], dtype=np.int64)


def match_score(tier: np.ndarray, human: np.ndarray) -> np.ndarray:
    """Tier A automatic (MPN, tax ID, exact name) 1; tier A by human approval 2; tier B 5.

    No link at all (a vendor on one side only) scores 1; tier C, which no
    in-range figure uses, scores as tier B.
    """
    tier = np.asarray(tier, dtype=object)
    return np.where(
        tier == "A",
        np.where(np.asarray(human, dtype=bool), 2, 1),
        np.where(pd.isna(tier), 1, 5),
    )


def complexity(scores: pd.DataFrame) -> np.ndarray:
    """Weighted average of the five factor scores (``score_<factor>`` columns)."""
    return sum(scores[f"score_{name}"].to_numpy() * w for name, w in WEIGHTS.items())


def wave(
    lever: np.ndarray, change_type: np.ndarray, available: np.ndarray, score: np.ndarray
) -> np.ndarray:
    """Wave 3 when available after month 12; wave 1 for quick same-vendor or terms changes."""
    quick = ((lever == 1) & (change_type == "same_vendor")) | (lever == 3)
    first = quick & (available <= WAVE1_MAX_AVAILABLE) & (score <= WAVE1_MAX_COMPLEXITY + 1e-12)
    return np.where(available > WAVE3_MIN_AVAILABLE, 3, np.where(first, 1, 2))


def prioritise(facts: pd.DataFrame) -> pd.DataFrame:
    """Factor scores, ``complexity`` and ``wave`` for each opportunity.

    ``facts`` needs ``lever``, ``change_type``, ``available_month``, ``change``
    (a ``CHANGE_SCORES`` key), ``criticality``, ``sites``, ``match_tier`` and
    ``match_human``.
    """
    scores = pd.DataFrame(
        {
            "score_contract": contract_score(facts["available_month"].to_numpy()),
            "score_change": facts["change"].map(CHANGE_SCORES).to_numpy(dtype=np.int64),
            "score_criticality": criticality_score(facts["criticality"].to_numpy()),
            "score_sites": sites_score(facts["sites"].to_numpy()),
            "score_match": match_score(facts["match_tier"], facts["match_human"]),
        },
        index=facts.index,
    )
    scores["complexity"] = complexity(scores)
    scores["wave"] = wave(
        facts["lever"].to_numpy(),
        facts["change_type"].to_numpy(),
        facts["available_month"].to_numpy(),
        scores["complexity"].to_numpy(),
    )
    return scores
