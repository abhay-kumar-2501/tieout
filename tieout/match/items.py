"""Item entity resolution (PRD 4.4): item records, pair scoring and one-to-one assembly.

Pipeline::

    lines --build_item_records--> item_records --match_items--> ItemMatch(item_map, pairs)

Scoring (skipped when ``cached_pairs`` is given):

* **I1** same valid normalised MPN from the ``mpn`` column, compatible
  manufacturers, same L2, different companies -> tier A; demoted to tier C with
  "same MPN, conflicting attributes" when the attribute parsers find a conflict.
* **I3** TF-IDF on character n-grams fitted once on every normalised
  description, scored per L2 as one sparse product per L2 with a threshold and
  top-k cut. Automatic (tier B) only at cosine >= ``auto_cosine`` with at least
  two critical attributes extracted on both sides and agreeing, no veto and no
  subset-only case; review (tier C) at cosine >= ``review_cosine`` without a
  veto. A part-number-like token in one description that equals the other
  record's MPN makes the pair an I3 candidate even below the review threshold.

Assembly (always re-run) takes candidates in the order I1, I3 automatic, I3
review; within each by descending score, ties by record key. A record matched
at tier A or B takes no further automatic match. Reviewer decisions are then
applied: rejected pairs are never proposed again; approved pairs become tier A
(stage ``human``) unless either side already has a tier A or B partner, in which
case the approval is blocked with a message naming that partner.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from tieout.match.attributes import (
    CRITICAL_KEYS,
    Attributes,
    Comparison,
    bare_numbers,
    compare,
    numeric_tokens,
    parse_attributes,
)
from tieout.match.differences import describe, unexplained_tokens
from tieout.normalise.items import (
    extract_mpn_like_tokens,
    item_key,
    manufacturers_compatible,
    mpn_key,
    normalise_description,
    normalise_manufacturer,
)
from tieout.normalise.packs import strip_pack_tokens
from tieout.normalise.truncation import cut_length

__all__ = [
    "ITEM_MAP_COLUMNS",
    "ITEM_RECORD_COLUMNS",
    "PAIR_COLUMNS",
    "TOP_K",
    "ItemMatch",
    "build_item_records",
    "match_items",
]

PAIR_TYPE = "item_match"
TOP_K = 25  # per record and direction, within an L2, for I3 candidates

ITEM_RECORD_COLUMNS = [
    "item_record_id",
    "company",
    "item_key",
    "item_code",
    "mpn",
    "manufacturer",
    "description",
    "l2_code",
    "family",
    "spend",
]
ITEM_MAP_COLUMNS = [
    "item_record_id",
    "company",
    "item_key",
    "canonical_item_id",
    "partner_id",
    "stage",
    "score",
    "tier",
    "attributes",
    "l2_code",
]
# Threshold-free scoring facts; these are what ``cached_pairs`` must carry.
SCORED_COLUMNS = [
    "pair_id",
    "type",
    "key_a",
    "key_b",
    "scored_stage",
    "score",
    "cosine",
    "conflict",
    "subset_only",
    "number_mismatch",
    "word_mismatch",
    "critical_agreements",
    "mpn_token",
    "facts",
]
PAIR_COLUMNS = [
    "pair_id",
    "type",
    "key_a",
    "key_b",
    "score",
    "stage",
    "tier",
    "evidence",
    "status",
    "scored_stage",
    "cosine",
    "conflict",
    "subset_only",
    "number_mismatch",
    "word_mismatch",
    "critical_agreements",
    "mpn_token",
    "facts",
]


@dataclass(frozen=True)
class ItemMatch:
    """Result of :func:`match_items`."""

    item_map: pd.DataFrame
    pairs: pd.DataFrame


# ------------------------------------------------------------------ records


def _clean(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value is pd.NA:
        return None
    text = str(value).strip()
    return text or None


def _most_frequent(df: pd.DataFrame, col: str, *, prefer_longest: bool = False) -> pd.Series:
    """Most frequent non-blank value per record; ties to the longest, then lexical."""
    sub = pd.DataFrame({"rid": df["item_record_id"], "v": df[col].map(_clean)}).dropna()
    if sub.empty:
        return pd.Series(dtype=object)
    counts = sub.groupby(["rid", "v"], sort=True).size().reset_index(name="n")
    counts["len"] = counts["v"].str.len()
    by = ["rid", "n", "len", "v"] if prefer_longest else ["rid", "n", "v"]
    asc = [True, False, False, True] if prefer_longest else [True, False, True]
    counts = counts.sort_values(by, ascending=asc, kind="mergesort")
    return counts.drop_duplicates("rid").set_index("rid")["v"]


def build_item_records(lines: pd.DataFrame) -> pd.DataFrame:
    """One row per item record (PRD 4.4) with a mapped L2.

    Only lines with an item code or MPN take part. The record key is the
    line's ``item_key`` when that column exists, otherwise it is derived
    (item code, else ``MPN:{mpn}|{manufacturer}``). The description is the
    most frequent one on the record's lines, ties going to the longest.
    """
    if lines.empty:
        return pd.DataFrame(columns=ITEM_RECORD_COLUMNS)
    df = lines.copy()
    for col in ("item_code", "mpn", "manufacturer", "item_description", "l2_code", "family"):
        if col not in df.columns:
            df[col] = None
    if "item_key" in df.columns:
        keys = df["item_key"].map(_clean)
    else:
        keys = pd.Series(
            [
                item_key(c, m, f)
                for c, m, f in zip(df["item_code"], df["mpn"], df["manufacturer"], strict=True)
            ],
            index=df.index,
            dtype=object,
        )
    df["item_key"] = keys
    df["l2_code"] = df["l2_code"].map(_clean)
    df = df[df["item_key"].notna() & df["l2_code"].notna()]
    if df.empty:
        return pd.DataFrame(columns=ITEM_RECORD_COLUMNS)
    df = df.assign(item_record_id=df["company"].astype(str) + ":" + df["item_key"].astype(str))
    amount = df["amount"] if "amount" in df.columns else pd.Series(0.0, index=df.index)
    df = df.assign(_amount=pd.to_numeric(amount, errors="coerce").fillna(0.0))

    base = (
        df.groupby("item_record_id", sort=True)
        .agg(company=("company", "first"), item_key=("item_key", "first"), spend=("_amount", "sum"))
        .reset_index()
    )
    out = base.set_index("item_record_id")
    out["description"] = _most_frequent(df, "item_description", prefer_longest=True)
    out["item_code"] = _most_frequent(df, "item_code")
    out["mpn"] = _most_frequent(df, "mpn")
    out["manufacturer"] = _most_frequent(df, "manufacturer")
    out["l2_code"] = _most_frequent(df, "l2_code")
    fam = df.assign(_l2=df["l2_code"]).merge(
        out["l2_code"].rename("_chosen"), left_on="item_record_id", right_index=True
    )
    fam = fam[fam["_l2"] == fam["_chosen"]]
    out["family"] = _most_frequent(fam, "family")
    if out["family"].isna().any():
        from tieout.reference import load_taxonomy

        lookup = dict(load_taxonomy()[["l2_code", "family"]].itertuples(index=False))
        out["family"] = out["family"].fillna(out["l2_code"].map(lookup))
    out["family"] = out["family"].fillna("generic").astype(str).str.strip().str.lower()
    out = out.reset_index()
    out = out.astype(object).where(out.notna(), None)
    out["spend"] = out["spend"].astype(float)
    return (
        out[ITEM_RECORD_COLUMNS]
        .sort_values("item_record_id", kind="mergesort")
        .reset_index(drop=True)
    )


# ------------------------------------------------------------------ prepare


@dataclass(frozen=True)
class _Prepared:
    ids: list[str]
    company: list[str]
    l2: list[str]
    family: list[str]
    norm: list[str]
    guard: list[str]
    raw: list[str]
    attrs: list[Attributes]
    mpn: list[str | None]
    manufacturer: list[str]
    raw_manufacturer: list[str | None]
    index: dict[str, int]


def _prepare(records: pd.DataFrame) -> tuple[pd.DataFrame, _Prepared]:
    recs = records.copy()
    for col in ITEM_RECORD_COLUMNS:
        if col not in recs.columns:
            recs[col] = None
    if recs["item_record_id"].isna().any():
        recs["item_record_id"] = recs["company"].astype(str) + ":" + recs["item_key"].astype(str)
    recs = recs.sort_values("item_record_id", kind="mergesort").reset_index(drop=True)
    norms: list[str] = []
    guards: list[str] = []
    raws: list[str] = []
    attrs: list[Attributes] = []
    cache: dict[tuple[str, str, bool], tuple[str, str, Attributes]] = {}
    families = [(_clean(f) or "generic").lower() for f in recs["family"]]
    limits = {
        str(company): cut_length(group["description"])
        for company, group in recs.groupby("company", sort=True)
    }
    for desc, fam, company in zip(recs["description"], families, recs["company"], strict=False):
        text = _clean(desc) or ""
        key = (text, fam, len(text) == limits.get(str(company)))
        if key not in cache:
            norm = normalise_description(strip_pack_tokens(text))
            # A description cut at its field length may end in a partial token
            # ("SCH 8" for "SCH 80"); attributes and guards ignore that token.
            guard = norm.rsplit(" ", 1)[0] if key[2] and " " in norm else norm
            cache[key] = (norm, guard, parse_attributes(guard, fam))
        norm, guard, parsed = cache[key]
        norms.append(norm)
        guards.append(guard)
        raws.append(strip_pack_tokens(text))
        attrs.append(parsed)
    ids = recs["item_record_id"].astype(str).tolist()
    prepared = _Prepared(
        ids=ids,
        company=recs["company"].astype(str).tolist(),
        l2=[_clean(v) or "" for v in recs["l2_code"]],
        family=families,
        norm=norms,
        guard=guards,
        raw=raws,
        attrs=attrs,
        mpn=[mpn_key(v) for v in recs["mpn"]],
        manufacturer=[normalise_manufacturer(v) for v in recs["manufacturer"]],
        raw_manufacturer=[_clean(v) for v in recs["manufacturer"]],
        index={rid: i for i, rid in enumerate(ids)},
    )
    return recs, prepared


# ------------------------------------------------------------------ scoring


def _pair_id(a: str, b: str) -> str:
    left, right = sorted((a, b))
    return f"{PAIR_TYPE}|{left}|{right}"


def _fmt_attrs(items: Iterable[tuple[str, str]]) -> str:
    return ", ".join(f"{k} {v}" if k != v else v for k, v in items)


def _unit_conflicts(text_a: str, text_b: str) -> list[tuple[str, str, str]]:
    """Backstop for parser families: the same unit stated with no value in common."""
    by_unit: list[dict[str, set[str]]] = []
    for text in (text_a, text_b):
        units: dict[str, set[str]] = defaultdict(set)
        for token in numeric_tokens(text):
            for part in _split_group(token):
                unit = part.lstrip("0123456789.")
                if unit:
                    units[unit].add(part)
        by_unit.append(units)
    out = []
    for unit in sorted(set(by_unit[0]) & set(by_unit[1])):
        va, vb = by_unit[0][unit], by_unit[1][unit]
        if not va & vb:
            out.append((f"{unit} value", ", ".join(sorted(va)), ", ".join(sorted(vb))))
    return out


def _split_group(token: str) -> list[str]:
    """``4.5X0.875IN`` -> ``['4.5IN', '0.875IN']``; units inherited from the last part."""
    parts = token.split("X")
    if len(parts) == 1:
        return parts
    unit = parts[-1].lstrip("0123456789.")
    return [p if p.lstrip("0123456789.") else p + unit for p in parts]


def _comparison_facts(cmp: Comparison) -> str:
    agree = _fmt_attrs(cmp.agreements) or "none"
    text = f"Agreeing attributes: {agree}."
    if cmp.conflicts:
        text += " Conflicting attributes: " + ", ".join(
            f"{k} {a} vs {b}" for k, a, b in cmp.conflicts
        )
        text += "."
    if cmp.subset_only:
        text += " One side's numeric attributes are a strict subset of the other's."
    return text


def _top_k_mask(rows: np.ndarray, cols: np.ndarray, vals: np.ndarray, k: int) -> np.ndarray:
    """Keep entries ranked within the top ``k`` of their row or of their column."""
    keep = np.zeros(len(vals), dtype=bool)
    for primary, secondary in ((rows, cols), (cols, rows)):
        order = np.lexsort((secondary, -vals, primary))
        sorted_primary = primary[order]
        starts = np.r_[0, np.flatnonzero(np.diff(sorted_primary)) + 1]
        group_start = np.repeat(starts, np.diff(np.r_[starts, len(order)]))
        rank = np.arange(len(order)) - group_start
        keep[order[rank < k]] = True
    return keep


def _score(prep: _Prepared, review_cosine: float, top_k: int) -> pd.DataFrame:
    n = len(prep.ids)
    if n == 0:
        return pd.DataFrame(columns=SCORED_COLUMNS)
    vectoriser = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=False)
    try:
        matrix = vectoriser.fit_transform(prep.norm).tocsr()
    except ValueError:  # every description is blank: no vocabulary, no I3
        matrix = sparse.csr_matrix((n, 1))

    by_l2: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for i in range(n):
        by_l2[prep.l2[i]][prep.company[i]].append(i)

    # candidate (acquirer-side index, target-side index) -> (stage, mpn token)
    candidates: dict[tuple[int, int], tuple[str, str | None]] = {}
    cosines: dict[tuple[int, int], float] = {}

    def ordered(i: int, j: int) -> tuple[int, int]:
        return (i, j) if prep.ids[i] < prep.ids[j] else (j, i)

    # I1: same valid MPN from the mpn column, compatible manufacturers, same L2.
    by_mpn: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i in range(n):
        if prep.mpn[i]:
            by_mpn[(prep.l2[i], prep.mpn[i])].append(i)  # type: ignore[arg-type]
    for members in by_mpn.values():
        for x, i in enumerate(members):
            for j in members[x + 1 :]:
                if prep.company[i] == prep.company[j]:
                    continue
                if manufacturers_compatible(prep.raw_manufacturer[i], prep.raw_manufacturer[j]):
                    candidates[ordered(i, j)] = ("I1", None)

    # I3: one sparse product per L2 with a threshold and top-k cut.
    for l2 in sorted(by_l2):
        companies = sorted(by_l2[l2])
        if len(companies) < 2:
            continue
        left = np.asarray(by_l2[l2][companies[0]])
        right = np.asarray(by_l2[l2][companies[1]])
        product = (matrix[left] @ matrix[right].T).tocoo()
        mask = product.data >= review_cosine - 1e-12
        rows, cols, vals = product.row[mask], product.col[mask], product.data[mask]
        if len(vals) == 0:
            continue
        keep = _top_k_mask(rows, cols, vals, top_k)
        for r, c, v in zip(rows[keep], cols[keep], vals[keep], strict=False):
            pair = ordered(int(left[r]), int(right[c]))
            cosines[pair] = float(v)
            candidates.setdefault(pair, ("I3", None))

    # MPN-like description tokens equal to the other side's MPN: I3 candidates only.
    for i in range(n):
        if not prep.raw[i]:
            continue
        for token in extract_mpn_like_tokens(prep.raw[i]):
            for j in by_mpn.get((prep.l2[i], token), []):
                if prep.company[i] == prep.company[j]:
                    continue
                pair = ordered(i, j)
                stage, _ = candidates.get(pair, ("I3", None))
                if stage == "I3":
                    candidates[pair] = ("I3", token)

    rows_out: list[dict[str, Any]] = []
    for (i, j), (stage, token) in sorted(candidates.items(), key=lambda kv: kv[0]):
        cosine = cosines.get((i, j))
        if cosine is None:
            cosine = float(matrix[i].multiply(matrix[j]).sum())
        family = prep.family[i]
        cmp = compare(prep.attrs[i], prep.attrs[j], family)
        conflicts = list(cmp.conflicts)
        if stage == "I3" and family in CRITICAL_KEYS:
            conflicts += _unit_conflicts(prep.norm[i], prep.norm[j])
        cmp = Comparison(cmp.family, cmp.agreements, tuple(conflicts), cmp.subset_only)
        mismatch = ""
        if stage == "I3":
            na, nb = bare_numbers(prep.norm[i]), bare_numbers(prep.norm[j])
            if na - nb and nb - na:
                mismatch = f"{', '.join(sorted(na - nb))} vs {', '.join(sorted(nb - na))}"
        difference = ""
        if stage == "I3" and not mismatch:
            only_a, only_b = unexplained_tokens(prep.norm[i], prep.norm[j])
            if only_a and only_b:
                difference = describe(only_a, only_b)
        if stage == "I3" and cosine < review_cosine - 1e-12 and token is None:
            continue
        a, b = prep.ids[i], prep.ids[j]
        if stage == "I1":
            ma, mb = prep.raw_manufacturer[i] or "blank", prep.raw_manufacturer[j] or "blank"
            facts = (
                f"I1 manufacturer part number: both records carry MPN {prep.mpn[i]} "
                f"(manufacturers {ma} / {mb}, compatible). Description similarity {cosine:.2f}. "
            )
            score = 1.0
        else:
            facts = f"I3 description similarity {cosine:.2f} (character n-gram TF-IDF). "
            if token:
                facts += f"Part number {token} appears in one description and as the other's MPN. "
            score = cosine
        facts += _comparison_facts(cmp)
        if mismatch:
            facts += f" Other numbers in the descriptions differ ({mismatch})."
        if difference:
            facts += f" Each description states something the other does not ({difference})."
        rows_out.append(
            {
                "pair_id": _pair_id(a, b),
                "type": PAIR_TYPE,
                "key_a": a,
                "key_b": b,
                "scored_stage": stage,
                "score": score,
                "cosine": cosine,
                "conflict": cmp.veto,
                "subset_only": cmp.subset_only,
                "number_mismatch": bool(mismatch),
                "word_mismatch": bool(difference),
                "critical_agreements": cmp.critical_agreements,
                "mpn_token": token,
                "facts": facts,
            }
        )
    if not rows_out:
        return pd.DataFrame(columns=SCORED_COLUMNS)
    return pd.DataFrame(rows_out, columns=SCORED_COLUMNS)


# ----------------------------------------------------------------- assembly


def _latest_decisions(decisions: pd.DataFrame | None) -> dict[str, str]:
    if decisions is None or len(decisions) == 0:
        return {}
    df = decisions.copy()
    if "type" in df.columns:
        df = df[df["type"].astype(str).str.strip() == PAIR_TYPE]
    if df.empty:
        return {}
    df = df.assign(
        _order=range(len(df)),
        _at=df["decided_at"].astype(str) if "decided_at" in df.columns else "",
    )
    df = df.sort_values(["pair_id", "_at", "_order"], kind="mergesort")
    latest = df.drop_duplicates("pair_id", keep="last")
    normal = {"approve": "approve", "approved": "approve", "reject": "reject"}
    normal |= {"rejected": "reject", "defer": "defer", "deferred": "defer"}
    out = {}
    for pid, dec in zip(latest["pair_id"], latest["decision"], strict=False):
        value = normal.get(str(dec).strip().lower())
        if value:
            out[str(pid)] = value
    return out


def _proposal(row: dict[str, Any], auto: float, review: float) -> tuple[str | None, str, str]:
    """Return (tier, status, sentence) before one-to-one assembly."""
    stage, cosine = row["scored_stage"], float(row["cosine"])
    if stage == "I1":
        if row["conflict"]:
            return "C", "pending", "Same MPN, conflicting attributes: tier C, sent to review."
        return "A", "auto", "Tier A: deterministic part-number match."
    if stage != "I3":
        return None, "dropped", ""
    if row["conflict"]:
        return None, "vetoed", "Vetoed: conflicting attributes rule out a match."
    agree = int(row["critical_agreements"])
    if (
        cosine >= auto - 1e-12
        and not row["subset_only"]
        and not row["number_mismatch"]
        and not row["word_mismatch"]
        and agree >= 2
    ):
        return (
            "B",
            "auto",
            f"Tier B: similarity {cosine:.2f} is at or above {auto:.2f} and "
            f"{agree} critical attributes agree with no conflict.",
        )
    if cosine >= review - 1e-12 or row["mpn_token"]:
        if cosine < auto - 1e-12:
            why = f"similarity {cosine:.2f} is below the automatic threshold {auto:.2f}"
        elif row["subset_only"]:
            why = "one side's numeric attributes are a subset of the other's"
        elif row["number_mismatch"]:
            why = "other numbers in the descriptions differ"
        elif row["word_mismatch"]:
            why = "each description states something the other does not"
        else:
            why = f"only {agree} critical attribute(s) agree on both sides (two needed)"
        return "C", "pending", f"Tier C, review only: {why}. Text similarity alone never matches."
    return None, "dropped", ""


def _assemble(
    scored: pd.DataFrame,
    prep: _Prepared,
    auto: float,
    review: float,
    decisions: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, tuple[str, str, str, float, str]]]:
    """One-to-one assembly and decisions. Returns pairs and accepted matches.

    The match dictionary maps each matched record to
    ``(partner, pair_id, stage, score, tier)``.
    """
    rows: dict[str, dict[str, Any]] = {}
    for rec in scored.to_dict("records"):
        if rec["key_a"] not in prep.index or rec["key_b"] not in prep.index:
            continue
        rec["mpn_token"] = _clean(rec["mpn_token"])
        rec["conflict"] = bool(rec["conflict"])
        rec["subset_only"] = bool(rec["subset_only"])
        rec["number_mismatch"] = bool(rec["number_mismatch"])
        rec["word_mismatch"] = bool(rec["word_mismatch"])
        rows[rec["pair_id"]] = dict(rec)

    # Approved pairs the matcher did not propose this run still count.
    for pid, dec in sorted(decisions.items()):
        if dec != "approve" or pid in rows:
            continue
        parts = pid.split("|")
        if len(parts) != 3 or parts[0] != PAIR_TYPE:
            continue
        a, b = parts[1], parts[2]
        if a not in prep.index or b not in prep.index:
            continue
        if prep.company[prep.index[a]] == prep.company[prep.index[b]]:
            continue
        rows[pid] = {
            "pair_id": pid,
            "type": PAIR_TYPE,
            "key_a": a,
            "key_b": b,
            "scored_stage": "human",
            "score": float("nan"),
            "cosine": float("nan"),
            "conflict": False,
            "subset_only": False,
            "number_mismatch": False,
            "word_mismatch": False,
            "critical_agreements": 0,
            "mpn_token": None,
            "facts": "Not proposed by the matcher in this run.",
        }

    group_of = {"A": 0, "B": 1, "C": 2}
    notes: dict[str, list[str]] = defaultdict(list)
    queue = []
    for pid, row in rows.items():
        if row["scored_stage"] == "human":
            row.update(tier=None, status="dropped", stage="human", sentence="")
            continue
        tier, status, sentence = _proposal(row, auto, review)
        row.update(tier=tier, status=status, stage=row["scored_stage"], sentence=sentence)
        if decisions.get(pid) == "reject":
            row.update(tier=None, status="rejected", sentence="Rejected by a reviewer.")
            continue
        if status in {"auto", "pending"}:
            group = 0 if row["scored_stage"] == "I1" else group_of[tier]  # type: ignore[index]
            queue.append((group, -float(row["score"]), row["key_a"], row["key_b"], pid))

    matched: dict[str, tuple[str, str]] = {}  # record -> (partner, pair_id)
    for _, _, a, b, pid in sorted(queue):
        row = rows[pid]
        if row["tier"] in {"A", "B"}:
            if a in matched or b in matched:
                taken = [
                    f"{r} is already matched to {matched[r][0]}" for r in (a, b) if r in matched
                ]
                row.update(tier="C", status="pending")
                notes[pid].append(f"Not matched automatically: {'; '.join(taken)}.")
            else:
                matched[a] = (b, pid)
                matched[b] = (a, pid)

    for pid, dec in sorted(decisions.items()):
        if dec != "approve" or pid not in rows:
            continue
        row = rows[pid]
        if row["status"] == "rejected":
            continue
        a, b = row["key_a"], row["key_b"]
        blockers = [
            f"{r} is already matched to {matched[r][0]}"
            for r in (a, b)
            if r in matched and matched[r][1] != pid
        ]
        if blockers:
            row.update(tier="C", status="pending")
            notes[pid].append(f"Approval blocked: {'; '.join(blockers)}.")
            continue
        row.update(tier="A", status="approved", stage="human")
        row["sentence"] = "Approved by a reviewer: tier A."
        matched[a] = (b, pid)
        matched[b] = (a, pid)

    for pid, row in rows.items():
        if row["status"] != "pending":
            continue
        if decisions.get(pid) == "defer":
            row["status"] = "deferred"
        if not any(n.startswith(("Not matched", "Approval blocked")) for n in notes[pid]):
            taken = [
                f"{r} is already matched to {matched[r][0]}"
                for r in (row["key_a"], row["key_b"])
                if r in matched and matched[r][1] != pid
            ]
            if taken:
                notes[pid].append(f"Note: {'; '.join(taken)}.")

    out_rows = []
    for pid in sorted(rows):
        row = rows[pid]
        if row["status"] == "dropped":
            continue
        evidence = " ".join(
            part for part in (row["facts"], row["sentence"], *notes[pid]) if part
        ).strip()
        out_rows.append({**row, "evidence": evidence})
    pairs = pd.DataFrame(out_rows, columns=PAIR_COLUMNS) if out_rows else _empty_pairs()
    if not pairs.empty:
        pairs = pairs.astype(object).where(pairs.notna(), None)
        for col in ("score", "cosine"):
            pairs[col] = pairs[col].astype(float)
        pairs["conflict"] = pairs["conflict"].astype(bool)
        pairs["subset_only"] = pairs["subset_only"].astype(bool)
        pairs["number_mismatch"] = pairs["number_mismatch"].astype(bool)
        pairs["word_mismatch"] = pairs["word_mismatch"].astype(bool)
        pairs["critical_agreements"] = pairs["critical_agreements"].astype(int)

    accepted: dict[str, tuple[str, str, str, float, str]] = {}
    for record, (partner, pid) in matched.items():
        row = rows[pid]
        accepted[record] = (partner, pid, row["stage"], float(row["score"]), row["tier"])
    return pairs, accepted


def _empty_pairs() -> pd.DataFrame:
    return pd.DataFrame(columns=PAIR_COLUMNS)


def _item_map(
    recs: pd.DataFrame, prep: _Prepared, accepted: dict[str, tuple[str, str, str, float, str]]
) -> pd.DataFrame:
    if not prep.ids:
        return pd.DataFrame(columns=ITEM_MAP_COLUMNS)
    smallest = {rid: min(rid, accepted[rid][0]) if rid in accepted else rid for rid in prep.ids}
    canonical = {
        root: f"CI{n:06d}" for n, root in enumerate(sorted(set(smallest.values())), start=1)
    }
    rows = []
    for i, rid in enumerate(prep.ids):
        match = accepted.get(rid)
        rows.append(
            {
                "item_record_id": rid,
                "company": prep.company[i],
                "item_key": recs.at[i, "item_key"],
                "canonical_item_id": canonical[smallest[rid]],
                "partner_id": match[0] if match else None,
                "stage": match[2] if match else "none",
                "score": match[3] if match else float("nan"),
                "tier": match[4] if match else None,
                "attributes": json.dumps(prep.attrs[i], sort_keys=True),
                "l2_code": prep.l2[i] or None,
            }
        )
    out = pd.DataFrame(rows, columns=ITEM_MAP_COLUMNS, dtype=object)
    out["score"] = out["score"].astype(float)
    return out


# --------------------------------------------------------------------- API


def match_items(
    records: pd.DataFrame,
    *,
    auto_cosine: float = 0.80,
    review_cosine: float = 0.60,
    decisions: pd.DataFrame | None = None,
    cached_pairs: pd.DataFrame | None = None,
) -> ItemMatch:
    """Match item records across companies (PRD 4.4) and apply review decisions.

    ``records`` is the output of :func:`build_item_records`. With
    ``cached_pairs`` (a previous ``ItemMatch.pairs``), pair scoring is skipped
    and only the proposal, one-to-one assembly and decisions re-run.
    """
    recs, prep = _prepare(records)
    if cached_pairs is None:
        scored = _score(prep, review_cosine, TOP_K)
    else:
        missing = [c for c in SCORED_COLUMNS if c not in cached_pairs.columns]
        if missing:
            raise ValueError(f"cached_pairs is missing columns: {', '.join(missing)}")
        scored = cached_pairs[SCORED_COLUMNS]
        scored = scored[scored["type"] == PAIR_TYPE]
    pairs, accepted = _assemble(
        scored, prep, auto_cosine, review_cosine, _latest_decisions(decisions)
    )
    return ItemMatch(item_map=_item_map(recs, prep, accepted), pairs=pairs)
