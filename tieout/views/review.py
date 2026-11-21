"""The review queue (PRD 6.5): the list, one candidate side by side, and progress.

All of it is hidden in the integration-office view (PRD 6.9).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pandas as pd

from tieout.match.review import latest_decisions, parse_pair_id
from tieout.views.common import MASKED, NOT_IN_VIEW, Unavailable, resolve_view, thousands

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "QUEUE_ITEM_COLUMNS",
    "bulk_approve_preview",
    "review_item",
    "review_progress",
    "review_queue_items",
]

QUEUE_ITEM_COLUMNS = [
    "pair_id",
    "type",
    "label_a",
    "label_b",
    "score",
    "stage",
    "status",
    "dollars_at_stake",
    "stake",
    "stake_line",
]
_TOKEN = re.compile(r"[A-Z0-9]+(?:[./-][A-Z0-9]+)*")
_SENTENCE = re.compile(r"(?<=[.)])\s+(?=[A-Z])")
#: Evidence sentences that argue against a match; everything else supports it.
_AGAINST = (
    "conflict",
    "differ",
    "does not",
    "vetoed",
    "review:",
    "review only",
    "capped",
    "below",
    "not merged",
    "already matched",
    "too large",
    "looks like",
    "may be freight",
)
_VENDOR_FIELDS = ("vendor_id", "vendor_name", "vendor_tax_id", "vendor_country")
_ITEM_FIELDS = ("item_code", "mpn", "manufacturer", "item_description", "uom", "pack_qty")


def _stake_line(row: pd.Series) -> str:
    """ "Approving adds $184k to the gross gap" (PRD 6.5), or the spend a vendor link touches."""
    if row["type"].startswith("vendor_"):
        return f"Approving links {thousands(row['dollars_at_stake'])} of annual spend."
    stake = row["stake"]
    if pd.isna(stake) or stake <= 0:
        return "Approving adds nothing to the gross gap."
    return f"Approving adds {thousands(stake)} to the gross gap."


def review_queue_items(
    results: Results, queue_type: str | None = None, view: str | None = None
) -> pd.DataFrame | Unavailable:
    """Undecided candidates, largest dollars at stake first (optionally one queue type)."""
    if resolve_view(results, view) == MASKED:
        return NOT_IN_VIEW
    queue = results.review_queue
    if queue_type is not None:
        queue = queue[queue["type"] == queue_type]
    out = queue.copy()
    out["stake_line"] = [_stake_line(row) for _, row in out.iterrows()]
    return out.reindex(columns=QUEUE_ITEM_COLUMNS).reset_index(drop=True)


def _tokens(text: object) -> list[str]:
    return _TOKEN.findall(str(text or "").upper())


def _differences(label_a: object, label_b: object) -> dict[str, list[str]]:
    """Tokens only on one side (highlighted) and tokens both share."""
    a, b = _tokens(label_a), _tokens(label_b)
    return {
        "only_a": [t for t in a if t not in b],
        "only_b": [t for t in b if t not in a],
        "shared": [t for t in a if t in b],
    }


def _evidence(text: object) -> dict[str, list[str]]:
    sentences = [s.strip() for s in _SENTENCE.split(str(text or "")) if s.strip()]
    against = [s for s in sentences if any(word in s.lower() for word in _AGAINST)]
    return {"for": [s for s in sentences if s not in against], "against": against}


def _first(lines: pd.DataFrame, column: str) -> object:
    values = lines[column].dropna() if column in lines.columns else pd.Series(dtype=object)
    return values.mode().iloc[0] if len(values) else None


def _record_card(results: Results, key: str, pair_type: str) -> dict[str, Any]:
    """One side of the comparison: the record's fields as received, its spend and its link."""
    company, record = key.split(":", 1)
    lines = results.lines
    if pair_type.startswith("vendor_"):
        own = lines[lines["vendor_key"] == key]
        vendor = results.vendor_map.set_index("vendor_key").loc[key]
        fields = {f: _first(own, f) for f in _VENDOR_FIELDS}
        link = {"legal_entity_id": vendor["legal_entity_id"], "parent_id": vendor["parent_id"]}
        spend = float(vendor["spend"])
    else:
        own = lines[(lines["company"] == company) & (lines["item_key"] == record)]
        item = results.item_map.set_index("item_record_id").loc[key]
        fields = {f: _first(own, f) for f in _ITEM_FIELDS}
        link = {"canonical_item_id": item["canonical_item_id"], "l2_code": item["l2_code"]}
        spend = float(item["spend"])
    return {
        "company": company,
        "key": key,
        "fields": fields,
        "spend": spend,
        "lines": len(own),
        **link,
    }


def review_item(
    results: Results, pair_id: str, view: str | None = None
) -> dict[str, Any] | Unavailable:
    """One candidate in focus: both records side by side, differences, evidence, stake."""
    if resolve_view(results, view) == MASKED:
        return NOT_IN_VIEW
    queue = results.review_queue.set_index("pair_id", drop=False)
    if pair_id not in queue.index:
        return Unavailable(f"{pair_id} is not in the review queue.")
    row = queue.loc[pair_id]
    # The keys come from the queue row: a record key may itself contain "|" (MPN-keyed items),
    # which a pair id cannot be split on.
    pair_type = str(row["type"])
    cards = [
        _record_card(results, side, pair_type) for side in sorted((row["key_a"], row["key_b"]))
    ]
    label = "vendor_name" if pair_type.startswith("vendor_") else "item_description"
    evidence = _evidence(row["evidence"])
    return {
        "pair_id": pair_id,
        "type": pair_type,
        "stage": row["stage"],
        "score": None if pd.isna(row["score"]) else float(row["score"]),
        "tier": row["tier"],
        "records": cards,
        "differences": _differences(cards[0]["fields"][label], cards[1]["fields"][label]),
        "evidence_for": evidence["for"],
        "evidence_against": evidence["against"],
        "message": row["message"],
        "dollars_at_stake": float(row["dollars_at_stake"]),
        "stake": None if pd.isna(row["stake"]) else float(row["stake"]),
        "stake_line": _stake_line(row),
    }


def _decided_spend(results: Results, pair_ids: list[str]) -> float:
    """Annual spend of both records of each decided pair (the queue's dollars at stake)."""
    vendors = results.vendor_map.set_index("vendor_key")["spend"]
    items = results.item_map.set_index("item_record_id")["spend"]
    total = 0.0
    for pair_id in pair_ids:
        pair_type, side_a, side_b = parse_pair_id(pair_id)
        spend = vendors if pair_type.startswith("vendor_") else items
        total += sum(float(spend.get(side, 0.0)) for side in (side_a, side_b))
    return total


def review_progress(results: Results, view: str | None = None) -> dict[str, Any] | Unavailable:
    """Decisions made and dollars cleared against what is still pending (progress bar)."""
    if resolve_view(results, view) == MASKED:
        return NOT_IN_VIEW
    latest = latest_decisions(results.review_log)
    cleared = latest[latest["decision"].isin(["approve", "reject"])]
    queue = results.review_queue
    cleared_dollars = _decided_spend(results, cleared["pair_id"].tolist())
    remaining = float(queue["dollars_at_stake"].sum())
    whole = cleared_dollars + remaining
    return {
        "decided": int(len(cleared)),
        "pending": int((queue["status"] == "pending").sum()),
        "deferred": int((queue["status"] == "deferred").sum()),
        "dollars_cleared": cleared_dollars,
        "dollars_remaining": remaining,
        "share_cleared": cleared_dollars / whole if whole > 0 else 0.0,
        "empty": queue.empty,
        "text": (
            "Nothing left to review"
            if queue.empty
            else f"{thousands(cleared_dollars)} cleared, {thousands(remaining)} still to review"
        ),
    }


def bulk_approve_preview(
    results: Results, queue_type: str, min_score: float | None = None, view: str | None = None
) -> dict[str, Any] | Unavailable:
    """What "approve all at or above ``min_score``" would touch, for one queue type (PRD 6.5).

    Scores are the type's own scale (vendors 0-100, items cosine 0-1); types with
    no score (unit flags, incoterms) are not bulk-approvable. With ``min_score``
    omitted the whole scored range is previewed.
    """
    if resolve_view(results, view) == MASKED:
        return NOT_IN_VIEW
    queue = results.review_queue
    queue = queue[(queue["type"] == queue_type) & (queue["status"] == "pending")]
    scored = queue[queue["score"].notna()]
    if scored.empty:
        return Unavailable(f"{queue_type} candidates have no score to approve in bulk.")
    low, high = float(scored["score"].min()), float(scored["score"].max())
    cut = low if min_score is None else float(min_score)
    chosen = scored[scored["score"] >= cut]
    dollars = float(chosen["dollars_at_stake"].sum())
    stake = float(chosen["stake"].fillna(0.0).sum())
    return {
        "type": queue_type,
        "min_score": cut,
        "score_low": low,
        "score_high": high,
        "pair_ids": chosen["pair_id"].tolist(),
        "count": int(len(chosen)),
        "dollars_at_stake": dollars,
        "stake": stake,
        "text": (
            f"{len(chosen):,} pairs, {thousands(dollars)} of annual spend"
            + (f", {thousands(stake)} added to the gross gap" if stake > 0 else "")
        ),
    }
