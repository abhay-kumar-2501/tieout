"""Staged vendor entity resolution (PRD 4.3) with review decisions (PRD 4.5).

Stages run over the union of both companies' vendor records:

- V1 tax ID merge, with a cluster-level veto on different tax IDs;
- reviewer approvals of ``vendor_match`` pairs (tier A, stage ``human``);
- V2 exact normalised name, split by tax ID where one country shows two IDs;
- V4 fuzzy candidates (blocking, score, guards) clustered by V5;
- V3 parent table and approved ``vendor_sibling`` pairs set ``parent_id`` only.

Records are processed in sorted ``vendor_key`` order, so the input row order
never changes the result.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler

from tieout.match.review import approved, deferred, make_pair_id, rejected
from tieout.normalise.vendors import (
    VendorName,
    normalise_country,
    normalise_tax_id,
    normalise_vendor_name,
)
from tieout.reference import load_descriptor_tokens, load_generic_tokens

__all__ = [
    "PAIR_COLUMNS",
    "RECORD_COLUMNS",
    "VENDOR_MAP_COLUMNS",
    "FuzzyScore",
    "NameScorer",
    "VendorMatch",
    "build_vendor_records",
    "match_vendors",
]

RECORD_COLUMNS: tuple[str, ...] = (
    "vendor_key",
    "company",
    "vendor_id",
    "vendor_name",
    "vendor_tax_id",
    "vendor_country",
    "spend",
)
VENDOR_MAP_COLUMNS: tuple[str, ...] = (
    "vendor_key",
    "company",
    "vendor_id",
    "vendor_name",
    "name_normalised",
    "legal_entity_id",
    "parent_id",
    "stage",
    "score",
    "tier",
    "evidence",
)
PAIR_COLUMNS: tuple[str, ...] = (
    "pair_id",
    "type",
    "key_a",
    "key_b",
    "score",
    "stage",
    "tier",
    "evidence",
    "status",
    "score_detail",
)

#: Score caps from the V4 guards.
CAP_WEAK_NAME = 91.0
CAP_DESCRIPTOR_CLASH = 74.0
CAP_ONE_DESCRIPTOR = 91.0
#: Rare-token share of distinct names, and the smallest count that still blocks.
RARE_TOKEN_SHARE = 0.01
RARE_TOKEN_MIN_COUNT = 3
PREFIX_LENGTH = 4

_STAGE_RANK = {"V1": 0, "V2": 1, "human": 2, "V4": 3}


# --------------------------------------------------------------------------- records


def _mode(values: Iterable[object]) -> object | None:
    """Most frequent non-blank value; ties go to the lexically smallest."""
    counts = Counter(str(v) for v in values if v is not None and not pd.isna(v) and str(v).strip())
    if not counts:
        return None
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def build_vendor_records(lines: pd.DataFrame) -> pd.DataFrame:
    """One row per ``vendor_key`` with the most frequent name, tax ID and country.

    ``spend`` is the sum of ``amount`` (falling back to ``line_amount``).
    """
    amount_col = "amount" if "amount" in lines.columns else "line_amount"
    rows = []
    for key, group in lines.groupby("vendor_key", sort=True):
        spend = pd.to_numeric(group[amount_col], errors="coerce").fillna(0.0).sum()
        rows.append(
            {
                "vendor_key": key,
                "company": _mode(group["company"]),
                "vendor_id": _mode(group["vendor_id"]),
                "vendor_name": _mode(group["vendor_name"]),
                "vendor_tax_id": _mode(group["vendor_tax_id"])
                if "vendor_tax_id" in group
                else None,
                "vendor_country": _mode(group["vendor_country"])
                if "vendor_country" in group
                else None,
                "spend": float(spend),
            }
        )
    return pd.DataFrame(rows, columns=list(RECORD_COLUMNS))


@dataclass(frozen=True)
class _Record:
    index: int
    key: str
    company: str
    vendor_id: str
    vendor_name: str
    name: VendorName
    tax: str | None
    country: str | None

    @property
    def tax_key(self) -> tuple[str, str] | None:
        """``(country, tax)`` when the tax ID is comparable (PRD 4.3 V1)."""
        return (self.country, self.tax) if self.tax and self.country else None


def _prepare_records(records: pd.DataFrame) -> list[_Record]:
    frame = records.sort_values("vendor_key", kind="stable").reset_index(drop=True)
    if frame["vendor_key"].duplicated().any():
        raise ValueError("vendor records must have one row per vendor_key")
    out = []
    for i, row in enumerate(frame.itertuples(index=False)):
        out.append(
            _Record(
                index=i,
                key=str(row.vendor_key),
                company=str(row.company),
                vendor_id=str(row.vendor_id),
                vendor_name="" if pd.isna(row.vendor_name) else str(row.vendor_name),
                name=normalise_vendor_name(row.vendor_name),
                tax=normalise_tax_id(getattr(row, "vendor_tax_id", None)),
                country=normalise_country(getattr(row, "vendor_country", None)),
            )
        )
    return out


def _tax_vetoed(a: _Record, b: _Record) -> bool:
    """Record-level veto: same country, both tax IDs present and different."""
    return (
        a.tax_key is not None
        and b.tax_key is not None
        and a.country == b.country
        and (a.tax != b.tax)
    )


# --------------------------------------------------------------------------- scoring


@dataclass(frozen=True)
class FuzzyScore:
    """A guarded V4 score with the parts that explain it."""

    score: float
    raw: float
    token_sort: float
    jaro_winkler: float
    cap_reason: str | None

    def describe(self, name_a: str, name_b: str) -> str:
        text = (
            f"Names '{name_a}' and '{name_b}' score {self.score:.1f} "
            f"(0.6 x token sort {self.token_sort:.1f} + 0.4 x Jaro-Winkler "
            f"{100 * self.jaro_winkler:.1f}, after removing generic words)"
        )
        if self.cap_reason:
            text += f"; capped because {self.cap_reason}"
        return text


@dataclass(frozen=True)
class _Prepared:
    text: str
    tokens: tuple[str, ...]
    descriptors: frozenset[str]


@dataclass
class NameScorer:
    """V4 score and guards (PRD 4.3), memoised by name pair."""

    generic: frozenset[str] = field(default_factory=load_generic_tokens)
    descriptors: frozenset[str] = field(default_factory=load_descriptor_tokens)
    _prepared: dict[str, _Prepared] = field(default_factory=dict, repr=False)
    _cache: dict[tuple[str, str], FuzzyScore] = field(default_factory=dict, repr=False)

    def prepare(self, name: str) -> _Prepared:
        """Strip generic tokens; fall back to the full name if nothing is left."""
        hit = self._prepared.get(name)
        if hit is None:
            tokens = tuple(t for t in name.split() if t not in self.generic)
            text = " ".join(tokens) if tokens else name
            hit = _Prepared(text, tokens, frozenset(tokens) & self.descriptors)
            self._prepared[name] = hit
        return hit

    def _cap(
        self, a: _Prepared, b: _Prepared, name_a: str, name_b: str
    ) -> tuple[float, str | None]:
        cap, reason = math.inf, None
        for prepared, name in ((a, name_a), (b, name_b)):
            if len(prepared.tokens) < 2 or len("".join(prepared.tokens)) < 6:
                cap = CAP_WEAK_NAME
                reason = (
                    f"'{name}' has fewer than two distinctive words or six letters "
                    "once generic words are removed (review at most)"
                )
                break
        if a.descriptors and b.descriptors and not (a.descriptors & b.descriptors):
            return CAP_DESCRIPTOR_CLASH, (
                f"the names carry different business descriptors "
                f"({', '.join(sorted(a.descriptors))} vs {', '.join(sorted(b.descriptors))})"
            )
        if bool(a.descriptors) != bool(b.descriptors) and cap > CAP_ONE_DESCRIPTOR:
            only = name_a if a.descriptors else name_b
            word = ", ".join(sorted(a.descriptors or b.descriptors))
            cap = CAP_ONE_DESCRIPTOR
            reason = f"only '{only}' has a business descriptor ({word}) (review at most)"
        return cap, reason

    def score(self, name_a: str, name_b: str) -> FuzzyScore:
        """Guarded score for two normalised names; symmetric."""
        key = (name_a, name_b) if name_a <= name_b else (name_b, name_a)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        a, b = self.prepare(key[0]), self.prepare(key[1])
        tsr = float(fuzz.token_sort_ratio(a.text, b.text))
        jw = float(JaroWinkler.normalized_similarity(a.text, b.text))
        raw = round(0.6 * tsr + 0.4 * 100.0 * jw, 2)
        cap, reason = self._cap(a, b, key[0], key[1])
        result = FuzzyScore(
            score=min(raw, cap),
            raw=raw,
            token_sort=tsr,
            jaro_winkler=jw,
            cap_reason=reason if raw > cap else None,
        )
        self._cache[key] = result
        return result


# --------------------------------------------------------------------------- blocking


def _blocks(names: list[str]) -> list[list[int]]:
    """Name-index blocks: shared rare token, or the same first four characters."""
    token_sets = [frozenset(n.split()) for n in names]
    df = Counter(t for tokens in token_sets for t in tokens)
    limit = max(RARE_TOKEN_SHARE * len(names), RARE_TOKEN_MIN_COUNT)
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, (name, tokens) in enumerate(zip(names, token_sets, strict=True)):
        by_key[("prefix", name[:PREFIX_LENGTH])].append(i)
        for token in tokens:
            if df[token] < limit:
                by_key[("token", token)].append(i)
    return [members for _, members in sorted(by_key.items()) if len(members) > 1]


def _candidate_name_pairs(
    names: list[str], scorer: NameScorer, floor: float
) -> list[tuple[int, int, FuzzyScore]]:
    """Blocked name pairs whose guarded score reaches ``floor``.

    ``process.cdist`` pre-filters each block on the unguarded score; survivors
    are re-scored exactly (with guards) by :class:`NameScorer`.
    """
    texts = [scorer.prepare(n).text for n in names]
    seen: set[tuple[int, int]] = set()
    for block in _blocks(names):
        block_texts = [texts[i] for i in block]
        tsr = process.cdist(
            block_texts, block_texts, scorer=fuzz.token_sort_ratio, dtype=np.float32
        )
        jw = process.cdist(
            block_texts, block_texts, scorer=JaroWinkler.normalized_similarity, dtype=np.float32
        )
        raw = 0.6 * tsr.astype(np.float64) + 40.0 * jw.astype(np.float64)
        rows, cols = np.nonzero(np.triu(raw >= floor - 0.05, k=1))
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            i, j = sorted((block[r], block[c]))
            seen.add((i, j))
    out = []
    for i, j in sorted(seen):
        result = scorer.score(names[i], names[j])
        if result.score >= floor:
            out.append((i, j, result))
    return out


# --------------------------------------------------------------------------- clusters


class _Clusters:
    """Union-find over records with per-cluster tax IDs, tested names and cannot-links."""

    def __init__(self, records: list[_Record], cannot_link: set[tuple[int, int]]) -> None:
        self._parent = list(range(len(records)))
        self.members: dict[int, list[int]] = {r.index: [r.index] for r in records}
        self.taxes: dict[int, dict[str, set[str]]] = {
            r.index: ({r.country: {r.tax}} if r.tax_key else {}) for r in records
        }
        self.tested: dict[int, set[str]] = {r.index: set() for r in records}
        self._cannot: dict[int, set[int]] = defaultdict(set)
        for a, b in cannot_link:
            self._cannot[a].add(b)
            self._cannot[b].add(a)

    def find(self, i: int) -> int:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]
            i = self._parent[i]
        return i

    def same(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)

    def tax_conflict(self, a: int, b: int) -> bool:
        """Cluster-level veto: some member of each has a different tax ID in one country."""
        ta, tb = self.taxes[self.find(a)], self.taxes[self.find(b)]
        for country, ids in ta.items():
            other = tb.get(country)
            if other and (len(ids | other) > 1):
                return True
        return False

    def rejected_link(self, a: int, b: int) -> bool:
        """A reviewer rejected a pair joining these two clusters."""
        rb = self.find(b)
        return any(self.find(p) == rb for m in self.members[self.find(a)] for p in self._cannot[m])

    def union(self, a: int, b: int, tested: Iterable[str] = ()) -> int:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            root, child = min(ra, rb), max(ra, rb)
            self._parent[child] = root
            self.members[root] = sorted(self.members[root] + self.members.pop(child))
            for country, ids in self.taxes.pop(child).items():
                self.taxes[root].setdefault(country, set()).update(ids)
            self.tested[root] |= self.tested.pop(child)
        root = self.find(a)
        self.tested[root].update(tested)
        return root

    def groups(self) -> list[list[int]]:
        """Clusters as sorted member lists, ordered by smallest member."""
        return sorted(self.members.values())


# --------------------------------------------------------------------------- pair log


@dataclass(frozen=True)
class _Link:
    stage: str
    score: float
    tier: str
    evidence: str


@dataclass
class _Context:
    records: list[_Record]
    by_key: dict[str, _Record]
    clusters: _Clusters
    scorer: NameScorer
    approved: frozenset[str]
    rejected: frozenset[str]
    deferred: frozenset[str]
    auto_threshold: float
    review_threshold: float
    rows: dict[str, dict[str, object]] = field(default_factory=dict)
    key_pairs: set[tuple[str, str]] = field(default_factory=set)
    links: dict[int, _Link] = field(default_factory=dict)

    def decision(self, pair_id: str) -> str | None:
        if pair_id in self.approved:
            return "approve"
        if pair_id in self.rejected:
            return "reject"
        if pair_id in self.deferred:
            return "defer"
        return None

    def add_row(
        self,
        pair_type: str,
        a: _Record,
        b: _Record,
        *,
        score: float,
        stage: str,
        tier: str | None,
        status: str,
        detail: str,
        outcome: str,
    ) -> None:
        key_a, key_b = sorted((a.key, b.key))
        pair_id = make_pair_id(pair_type, key_a, key_b)
        if pair_id in self.rows:
            return
        self.key_pairs.add((key_a, key_b))
        self.rows[pair_id] = {
            "pair_id": pair_id,
            "type": pair_type,
            "key_a": key_a,
            "key_b": key_b,
            "score": float(score),
            "stage": stage,
            "tier": tier,
            "evidence": f"{detail}. {outcome}" if outcome else detail,
            "status": status,
            "score_detail": detail,
        }

    def link(self, record: _Record, stage: str, score: float, tier: str, evidence: str) -> None:
        """Keep the strongest link per record (stage rank, then higher score)."""
        new = _Link(stage, score, tier, evidence)
        old = self.links.get(record.index)
        if old is None or (_STAGE_RANK[stage], -score) < (_STAGE_RANK[old.stage], -old.score):
            self.links[record.index] = new


def _pair_records(ctx: _Context, pair_id: str) -> tuple[_Record, _Record] | None:
    _, key_a, key_b = pair_id.split("|")
    a, b = ctx.by_key.get(key_a), ctx.by_key.get(key_b)
    return (a, b) if a is not None and b is not None else None


def _review_status(ctx: _Context, pair_id: str) -> tuple[str, str | None]:
    """Status and tier for a queue item given any reviewer decision."""
    decision = ctx.decision(pair_id)
    if decision == "approve":
        return "approved", "A"
    if decision == "reject":
        return "rejected", None
    if decision == "defer":
        return "deferred", "C"
    return "pending", "C"


# --------------------------------------------------------------------------- V1


def _apply_tax_ids(ctx: _Context) -> None:
    """V1: merge records sharing a tax ID within one country (tier A)."""
    groups: dict[tuple[str, str], list[_Record]] = defaultdict(list)
    for record in ctx.records:
        if record.tax_key:
            groups[record.tax_key].append(record)
    for (country, tax), members in sorted(groups.items()):
        anchor = members[0]
        for member in members[1:]:
            ctx.clusters.union(anchor.index, member.index)
            detail = f"Same tax ID {tax} in country {country}"
            ctx.add_row(
                "vendor_match",
                anchor,
                member,
                score=100.0,
                stage="V1",
                tier="A",
                status="auto",
                detail=detail,
                outcome="Merged automatically (tier A)",
            )
            for record in (anchor, member):
                ctx.link(record, "V1", 100.0, "A", detail)


# --------------------------------------------------------------------------- human


def _apply_approvals(ctx: _Context) -> None:
    """Reviewer-approved ``vendor_match`` pairs merge at tier A (stage ``human``)."""
    for pair_id in sorted(p for p in ctx.approved if p.startswith("vendor_match|")):
        pair = _pair_records(ctx, pair_id)
        if pair is None:
            continue
        a, b = pair
        ctx.clusters.union(a.index, b.index)
        detail = "Approved as the same legal entity by a reviewer"
        for record in (a, b):
            ctx.link(record, "human", 100.0, "A", detail)


def _add_missing_approval_rows(ctx: _Context) -> None:
    for pair_id in sorted(ctx.approved):
        pair = _pair_records(ctx, pair_id)
        if pair is None or pair_id in ctx.rows or not pair_id.startswith("vendor_"):
            continue
        a, b = pair
        ctx.add_row(
            pair_id.split("|")[0],
            a,
            b,
            score=math.nan,
            stage="human",
            tier="A",
            status="approved",
            detail="Linked by a reviewer",
            outcome="",
        )


# --------------------------------------------------------------------------- V2


def _name_groups(records: list[_Record]) -> dict[str, list[_Record]]:
    groups: dict[str, list[_Record]] = defaultdict(list)
    for record in records:
        for name in record.name.names:
            groups[name].append(record)
    return groups


def _has_tax_split(members: list[_Record]) -> bool:
    by_country: dict[str, set[str]] = defaultdict(set)
    for record in members:
        if record.tax_key:
            country, tax = record.tax_key
            by_country[country].add(tax)
    return any(len(ids) > 1 for ids in by_country.values())


def _queue_exact(ctx: _Context, a: _Record, b: _Record, name: str, reason: str) -> None:
    """Send an exact-name pair that was not merged to review (sibling if vetoed)."""
    detail = f"Same normalised name '{name}'"
    if _tax_vetoed(a, b):
        pair_type = "vendor_sibling"
        reason = (
            f"Different tax IDs in {a.country} ({a.tax} vs {b.tax}): not merged; "
            "offered as possible sibling companies"
        )
    else:
        pair_type = "vendor_match"
    pair_id = make_pair_id(pair_type, a.key, b.key)
    status, tier = _review_status(ctx, pair_id)
    ctx.add_row(
        pair_type,
        a,
        b,
        score=100.0,
        stage="V2",
        tier=tier,
        status=status,
        detail=detail,
        outcome=reason,
    )


def _split_group(ctx: _Context, name: str, members: list[_Record]) -> None:
    """Two or more tax IDs in one country: keep each tax ID apart, review the rest."""
    units: dict[object, list[_Record]] = defaultdict(list)
    for record in members:
        units[record.tax_key or ("", record.key)].append(record)
    reps = sorted((unit[0] for unit in units.values()), key=lambda r: r.key)
    reason = (
        "Not merged automatically: records with this name carry different tax IDs, "
        "so the record cannot be assigned to one of them without review"
    )
    for a, b in combinations(reps, 2):
        _queue_exact(ctx, a, b, name, reason)


def _merge_group(ctx: _Context, name: str, members: list[_Record]) -> None:
    anchor = members[0]
    detail = f"Same normalised name '{name}'"
    for member in members[1:]:
        pair_id = make_pair_id("vendor_match", anchor.key, member.key)
        clusters = ctx.clusters
        if pair_id in ctx.rejected:
            status, tier = _review_status(ctx, pair_id)
            ctx.add_row(
                "vendor_match",
                anchor,
                member,
                score=100.0,
                stage="V2",
                tier=tier,
                status=status,
                detail=detail,
                outcome="Rejected by a reviewer",
            )
            continue
        if not clusters.same(anchor.index, member.index):
            if clusters.tax_conflict(anchor.index, member.index):
                _queue_exact(
                    ctx,
                    anchor,
                    member,
                    name,
                    "Not merged: the two legal entities hold different tax IDs in one country",
                )
                continue
            if clusters.rejected_link(anchor.index, member.index):
                _queue_exact(
                    ctx,
                    anchor,
                    member,
                    name,
                    "Not merged: a reviewer rejected a link between these legal entities",
                )
                continue
        tested = {name} if name in (anchor.name.name, member.name.name) else set()
        clusters.union(anchor.index, member.index, tested)
        status = "approved" if pair_id in ctx.approved else "auto"
        ctx.add_row(
            "vendor_match",
            anchor,
            member,
            score=100.0,
            stage="V2",
            tier="A",
            status=status,
            detail=detail,
            outcome="Merged automatically (tier A)",
        )
        for record in (anchor, member):
            ctx.link(record, "V2", 100.0, "A", detail)


def _apply_exact_names(ctx: _Context) -> None:
    """V2: exact normalised name (primary or alias) merges at tier A unless vetoed."""
    for name, members in sorted(_name_groups(ctx.records).items()):
        if len(members) < 2:
            continue
        if _has_tax_split(members):
            _split_group(ctx, name, members)
        else:
            _merge_group(ctx, name, members)


# --------------------------------------------------------------------------- V4 / V5


@dataclass(frozen=True)
class _Candidate:
    a: _Record
    b: _Record
    score: float
    detail: str


def _fresh_candidates(ctx: _Context) -> list[_Candidate]:
    """V4: score blocked pairs of distinct primary names, expanded to record pairs."""
    by_name: dict[str, list[_Record]] = defaultdict(list)
    for record in ctx.records:
        if record.name.name:
            by_name[record.name.name].append(record)
    names = sorted(by_name)
    out = []
    for i, j, result in _candidate_name_pairs(names, ctx.scorer, ctx.review_threshold):
        detail = result.describe(names[i], names[j])
        for a in by_name[names[i]]:
            for b in by_name[names[j]]:
                first, second = sorted((a, b), key=lambda r: r.key)
                out.append(_Candidate(first, second, result.score, detail))
    return out


def _cached_candidates(ctx: _Context, cached_pairs: pd.DataFrame) -> list[_Candidate]:
    """V4 candidates from a previous run's ``pairs`` (no scoring)."""
    rows = cached_pairs.loc[cached_pairs["stage"] == "V4"]
    out: dict[tuple[str, str], _Candidate] = {}
    for row in rows.itertuples(index=False):
        a, b = ctx.by_key.get(str(row.key_a)), ctx.by_key.get(str(row.key_b))
        if a is None or b is None or float(row.score) < ctx.review_threshold:
            continue
        first, second = sorted((a, b), key=lambda r: r.key)
        detail = str(getattr(row, "score_detail", row.evidence))
        out.setdefault((first.key, second.key), _Candidate(first, second, float(row.score), detail))
    return list(out.values())


def _chain_failure(ctx: _Context, a: _Record, b: _Record) -> str | None:
    """V5 anti-chaining test: each side's names score >= review threshold against the other's."""
    clusters = ctx.clusters
    names_a = sorted(clusters.tested[clusters.find(a.index)] | {a.name.name})
    names_b = sorted(clusters.tested[clusters.find(b.index)] | {b.name.name})
    for x in names_a:
        for y in names_b:
            if x == y:
                continue
            result = ctx.scorer.score(x, y)
            if result.score < ctx.review_threshold:
                return (
                    f"Not merged automatically: '{y}' scores only {result.score:.1f} against "
                    f"'{x}', already in the same legal entity (needs {ctx.review_threshold:g})"
                )
    return None


def _cluster_one(ctx: _Context, cand: _Candidate) -> None:
    a, b, clusters = cand.a, cand.b, ctx.clusters
    if _tax_vetoed(a, b):
        if cand.score >= ctx.auto_threshold:
            pair_id = make_pair_id("vendor_sibling", a.key, b.key)
            status, tier = _review_status(ctx, pair_id)
            outcome = (
                f"Different tax IDs in {a.country} ({a.tax} vs {b.tax}): not merged; "
                "offered as possible sibling companies"
            )
            ctx.add_row(
                "vendor_sibling",
                a,
                b,
                score=cand.score,
                stage="V4",
                tier=tier,
                status=status,
                detail=cand.detail,
                outcome=outcome,
            )
        else:
            ctx.add_row(
                "vendor_match",
                a,
                b,
                score=cand.score,
                stage="V4",
                tier=None,
                status="vetoed",
                detail=cand.detail,
                outcome=f"Vetoed: different tax IDs in {a.country}",
            )
        return
    pair_id = make_pair_id("vendor_match", a.key, b.key)
    decision = ctx.decision(pair_id)
    if decision in ("approve", "reject"):
        status, tier = _review_status(ctx, pair_id)
        outcome = "Approved by a reviewer" if decision == "approve" else "Rejected by a reviewer"
        ctx.add_row(
            "vendor_match",
            a,
            b,
            score=cand.score,
            stage="V4",
            tier=tier,
            status=status,
            detail=cand.detail,
            outcome=outcome,
        )
        return
    if clusters.same(a.index, b.index):
        ctx.add_row(
            "vendor_match",
            a,
            b,
            score=cand.score,
            stage="V4",
            tier="B",
            status="auto",
            detail=cand.detail,
            outcome="Already in the same legal entity",
        )
        return
    reason = _auto_block_reason(ctx, cand)
    if reason is None:
        clusters.union(a.index, b.index, {a.name.name, b.name.name})
        ctx.add_row(
            "vendor_match",
            a,
            b,
            score=cand.score,
            stage="V4",
            tier="B",
            status="auto",
            detail=cand.detail,
            outcome="Merged automatically (tier B): passed every guard",
        )
        for record in (a, b):
            ctx.link(record, "V4", cand.score, "B", cand.detail)
        return
    status, tier = _review_status(ctx, pair_id)
    ctx.add_row(
        "vendor_match",
        a,
        b,
        score=cand.score,
        stage="V4",
        tier=tier,
        status=status,
        detail=cand.detail,
        outcome=reason,
    )


def _auto_block_reason(ctx: _Context, cand: _Candidate) -> str | None:
    """Why a candidate is not merged automatically, or ``None`` if it may be."""
    if cand.score < ctx.auto_threshold:
        return (
            f"Review: score is between {ctx.review_threshold:g} and {ctx.auto_threshold:g} "
            "(tier C, treated as different vendors until approved)"
        )
    clusters = ctx.clusters
    if clusters.tax_conflict(cand.a.index, cand.b.index):
        return "Not merged automatically: the legal entities hold different tax IDs in one country"
    if clusters.rejected_link(cand.a.index, cand.b.index):
        return "Not merged automatically: a reviewer rejected a link between these legal entities"
    return _chain_failure(ctx, cand.a, cand.b)


def _apply_fuzzy(ctx: _Context, candidates: list[_Candidate]) -> None:
    """V5: descending score, ties by record keys; exact-name pairs are left to V2."""
    ordered = sorted(candidates, key=lambda c: (-c.score, c.a.key, c.b.key))
    for cand in ordered:
        if (cand.a.key, cand.b.key) in ctx.key_pairs:
            continue
        _cluster_one(ctx, cand)


def _settle_pending(ctx: _Context) -> None:
    """Pending ``vendor_match`` pairs already joined by other evidence need no review."""
    for row in ctx.rows.values():
        if row["type"] != "vendor_match" or row["status"] not in ("pending", "deferred"):
            continue
        a, b = ctx.by_key[str(row["key_a"])], ctx.by_key[str(row["key_b"])]
        if ctx.clusters.same(a.index, b.index):
            row["status"] = "auto"
            row["tier"] = "B" if row["stage"] == "V4" else "A"
            row["evidence"] = f"{row['score_detail']}. Already in the same legal entity"


# --------------------------------------------------------------------------- V3 / ids


def _parent_links(records: list[_Record], parents: pd.DataFrame | None) -> dict[int, str]:
    """V3: record index -> ``P:<normalised parent>`` from ``vendor_parents.csv``."""
    if parents is None or parents.empty:
        return {}
    by_name: dict[str, list[_Record]] = _name_groups(records)
    by_tax: dict[str, list[_Record]] = defaultdict(list)
    for record in records:
        if record.tax:
            by_tax[record.tax].append(record)
    links: dict[int, set[str]] = defaultdict(set)
    for row in parents.itertuples(index=False):
        parent = normalise_vendor_name(row.parent_name).name
        if not parent:
            continue
        country = normalise_country(getattr(row, "country", None))
        key_type = str(row.key_type).strip().lower()
        if key_type == "name":
            hits = by_name.get(normalise_vendor_name(row.key).name, [])
        elif key_type == "tax_id":
            hits = by_tax.get(normalise_tax_id(row.key) or "", [])
        else:
            raise ValueError(
                f"vendor_parents key_type must be 'name' or 'tax_id', got {key_type!r}"
            )
        for record in hits:
            if country is None or record.country == country:
                links[record.index].add(f"P:{parent}")
    return {i: min(ids) for i, ids in links.items()}


def _legal_entity_ids(clusters: _Clusters) -> dict[int, str]:
    groups = clusters.groups()
    width = max(5, len(str(len(groups))))
    return {m: f"LE{n:0{width}d}" for n, group in enumerate(groups, 1) for m in group}


def _parent_ids(
    ctx: _Context, le_ids: dict[int, str], table: dict[int, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """``parent_id`` per legal entity, and a note on where it came from."""
    le_parent: dict[str, str] = {}
    for index, parent in sorted(table.items()):
        le = le_ids[index]
        le_parent[le] = min(le_parent.get(le, parent), parent)
    # Approved siblings: union legal entities, then pick one parent per group.
    root: dict[str, str] = {le: le for le in set(le_ids.values())}

    def find(x: str) -> str:
        while root[x] != x:
            x = root[x]
        return x

    for pair_id in sorted(p for p in ctx.approved if p.startswith("vendor_sibling|")):
        pair = _pair_records(ctx, pair_id)
        if pair is None:
            continue
        ra, rb = find(le_ids[pair[0].index]), find(le_ids[pair[1].index])
        if ra != rb:
            root[max(ra, rb)] = min(ra, rb)
    groups: dict[str, list[str]] = defaultdict(list)
    for le in sorted(root):
        groups[find(le)].append(le)
    out: dict[str, str] = {}
    notes: dict[str, str] = {}
    for les in groups.values():
        listed = sorted(le_parent[le] for le in les if le in le_parent)
        parent = listed[0] if listed else les[0]
        for le in les:
            out[le] = parent
            if le in le_parent:
                notes[le] = f"Parent '{le_parent[le][2:]}' from the parent table (tier A)"
            elif len(les) > 1:
                notes[le] = "Shares a parent with a reviewer-approved sibling company"
    return out, notes


def _vendor_map(ctx: _Context, parents: pd.DataFrame | None) -> pd.DataFrame:
    le_ids = _legal_entity_ids(ctx.clusters)
    table = _parent_links(ctx.records, parents)
    parent_of, notes = _parent_ids(ctx, le_ids, table)
    rows = []
    for record in ctx.records:
        le = le_ids[record.index]
        link = ctx.links.get(record.index)
        size = len(ctx.clusters.members[ctx.clusters.find(record.index)])
        if link is not None and size > 1:
            stage, score, tier, evidence = link.stage, link.score, link.tier, link.evidence
        elif record.index in table:
            stage, score, tier, evidence = "V3", math.nan, "A", ""
        else:
            stage, score, tier, evidence = "none", math.nan, None, "No match found"
        note = notes.get(le)
        evidence = "; ".join(t for t in (evidence, note) if t)
        rows.append(
            {
                "vendor_key": record.key,
                "company": record.company,
                "vendor_id": record.vendor_id,
                "vendor_name": record.vendor_name,
                "name_normalised": record.name.name,
                "legal_entity_id": le,
                "parent_id": parent_of[le],
                "stage": stage,
                "score": score,
                "tier": tier,
                "evidence": evidence,
            }
        )
    return pd.DataFrame(rows, columns=list(VENDOR_MAP_COLUMNS))


def _pairs_frame(ctx: _Context) -> pd.DataFrame:
    frame = pd.DataFrame(list(ctx.rows.values()), columns=list(PAIR_COLUMNS))
    frame["score"] = frame["score"].astype(float)
    return frame.sort_values("pair_id", kind="stable").reset_index(drop=True)


# --------------------------------------------------------------------------- entry point


@dataclass(frozen=True)
class VendorMatch:
    """Result of :func:`match_vendors`: one row per record, and the pair log."""

    vendor_map: pd.DataFrame
    pairs: pd.DataFrame


def _cannot_links(by_key: dict[str, _Record], ids: frozenset[str]) -> set[tuple[int, int]]:
    out = set()
    for pair_id in ids:
        _, key_a, key_b = pair_id.split("|")
        if key_a in by_key and key_b in by_key:
            out.add((by_key[key_a].index, by_key[key_b].index))
    return out


def match_vendors(
    records: pd.DataFrame,
    parents: pd.DataFrame | None = None,
    *,
    auto_threshold: float = 92.0,
    review_threshold: float = 75.0,
    decisions: pd.DataFrame | None = None,
    cached_pairs: pd.DataFrame | None = None,
) -> VendorMatch:
    """Resolve vendor records into legal entities and parents (PRD 4.3, 4.5).

    ``records`` follows the ``vendor_records`` contract; ``parents`` the
    ``vendor_parents.csv`` columns. With ``cached_pairs`` (a previous
    ``pairs`` frame) V4 scoring is skipped and only clustering re-runs.
    """
    prepared = _prepare_records(records)
    by_key = {r.key: r for r in prepared}
    rejected_ids = rejected(decisions)
    ctx = _Context(
        records=prepared,
        by_key=by_key,
        clusters=_Clusters(prepared, _cannot_links(by_key, rejected(decisions, "vendor_match"))),
        scorer=NameScorer(),
        approved=approved(decisions),
        rejected=rejected_ids,
        deferred=deferred(decisions),
        auto_threshold=auto_threshold,
        review_threshold=review_threshold,
    )
    _apply_tax_ids(ctx)
    _apply_approvals(ctx)
    _apply_exact_names(ctx)
    if cached_pairs is None:
        candidates = _fresh_candidates(ctx)
    else:
        candidates = _cached_candidates(ctx, cached_pairs)
    _apply_fuzzy(ctx, candidates)
    _settle_pending(ctx)
    _add_missing_approval_rows(ctx)
    return VendorMatch(vendor_map=_vendor_map(ctx, parents), pairs=_pairs_frame(ctx))
