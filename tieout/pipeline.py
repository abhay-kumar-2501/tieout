"""The engine pipeline: load, prepare, match vendors, match items, assemble ``Results``.

``run_pipeline`` is the single entry point every surface uses (PRD 9.2)::

    load -> prepare -> vendor matching -> item matching -> Results

The synergy stages of PRD 5 (levers, bridge, risk, phasing) plug in after
matching, at the marked seam in :func:`run_pipeline`; until they exist the
synergy frames, ``totals`` and ``trace`` of the returned ``Results`` stay empty.
"""

from __future__ import annotations

import datetime as dt
import io
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from tieout.assumptions import merge_overrides, validate
from tieout.ingest import Prepared, load_file, prepare
from tieout.match import (
    ItemMatch,
    VendorMatch,
    build_item_records,
    build_vendor_records,
    match_items,
    match_vendors,
    read_decisions_csv,
    validate_decisions,
)
from tieout.normalise.taxonomy import suggest_categories
from tieout.reference import Thresholds, load_fx_rates, load_taxonomy, load_thresholds
from tieout.results import Results

__all__ = [
    "REVIEW_QUEUE_COLUMNS",
    "Matching",
    "PipelineInputs",
    "match_lines",
    "run_pipeline",
]

PathLike = str | Path
Table = pd.DataFrame | PathLike
ColumnMapping = Mapping[str, str] | Mapping[str, Mapping[str, str]]

COMPANIES = ("acquirer", "target")
PARENT_COLUMNS = ("key_type", "key", "country", "parent_name")
CATEGORY_MAP_COLUMNS = ("company", "category_native", "l2_code")
REVIEW_QUEUE_COLUMNS = (
    "pair_id",
    "type",
    "key_a",
    "key_b",
    "label_a",
    "label_b",
    "score",
    "stage",
    "tier",
    "status",
    "evidence",
    "spend_a",
    "spend_b",
    "dollars_at_stake",
)
_UNDECIDED = ("pending", "deferred")
STAGES_RUN = ("ingest", "vendor_matching", "item_matching")


@dataclass(frozen=True)
class PipelineInputs:
    """Everything one run reads. Files may be given as paths or as frames.

    ``acquirer`` and ``target`` are purchasing files (PRD 3.1) or raw frames with
    the schema column names. ``mapping`` maps file headers to schema names,
    either one mapping for both files or ``{"acquirer": {...}, "target": {...}}``.
    Without ``category_map`` the top category suggestion scoring at least 0.3 is
    accepted (PRD 9.2). ``assumptions`` overrides the defaults (a mapping or a
    TOML file); ``decisions`` is a review decisions log (PRD 4.5).
    ``category_settings`` is read by the synergy stages.
    """

    acquirer: Table
    target: Table
    mapping: ColumnMapping | None = None
    category_map: Table | None = None
    vendor_parents: Table | None = None
    fx: Mapping[str, float] | Table | None = None
    category_settings: Table | None = None
    assumptions: Mapping[str, Any] | PathLike | None = None
    decisions: Table | None = None
    period_end: str | None = None
    as_of: str | None = None
    aggregated: bool = False
    view: str = "clean"
    thresholds: Thresholds | None = None
    scenario: str = "custom"
    seed: int | None = None


@dataclass(frozen=True)
class Matching:
    """Vendor and item matching for one set of ``lines``."""

    vendor_records: pd.DataFrame
    item_records: pd.DataFrame
    vendors: VendorMatch
    items: ItemMatch


# --------------------------------------------------------------------------- loading


def _read_csv(source: Table) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy()
    return pd.read_csv(source, dtype=str, keep_default_na=False)


def _company_mapping(mapping: ColumnMapping | None, company: str) -> Mapping[str, str] | None:
    if mapping is None:
        return None
    per_company = mapping.get(company)
    if isinstance(per_company, Mapping):
        return per_company
    if any(isinstance(v, Mapping) for v in mapping.values()):
        return None
    return mapping  # type: ignore[return-value]


def _load(source: Table, company: str, mapping: ColumnMapping | None) -> pd.DataFrame:
    """A raw frame from a path, or from a frame passed through the same reader."""
    columns = _company_mapping(mapping, company)
    if isinstance(source, pd.DataFrame):
        buffer = io.StringIO(source.to_csv(index=False))
        return load_file(buffer, company, columns)
    return load_file(source, company, columns)


def _with_columns(
    frame: pd.DataFrame, columns: tuple[str, ...], name: str, optional: tuple[str, ...] = ()
) -> pd.DataFrame:
    """``frame`` reduced to ``columns``; ``optional`` ones are added blank when absent."""
    frame = frame.assign(**{c: "" for c in optional if c not in frame.columns})
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    return frame[list(columns)].reset_index(drop=True)


def _fx(fx: Mapping[str, float] | Table | None) -> Mapping[str, float] | pd.DataFrame:
    if fx is None:
        return load_fx_rates()
    if isinstance(fx, Mapping):
        return fx
    if isinstance(fx, pd.DataFrame):
        return fx
    return load_fx_rates(fx)


def _assumptions(inputs: PipelineInputs, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    given: Mapping[str, Any] | None
    if overrides is not None:
        given = overrides
    elif isinstance(inputs.assumptions, str | Path):
        given = tomllib.loads(Path(inputs.assumptions).read_text(encoding="utf-8"))
    else:
        given = inputs.assumptions
    merged = merge_overrides(given)
    validate(merged)
    return merged


def _decisions(given: Table | None) -> pd.DataFrame:
    if given is None:
        return validate_decisions(None)
    if isinstance(given, pd.DataFrame):
        return validate_decisions(given)
    return read_decisions_csv(given)


# --------------------------------------------------------------------------- stages


def _prepare(
    inputs: PipelineInputs, acq: pd.DataFrame, tgt: pd.DataFrame, taxonomy: pd.DataFrame
) -> tuple[Prepared, dict[str, Any]]:
    """Prepare the lines, suggesting the category map when none is supplied."""
    fx = _fx(inputs.fx)
    kwargs: dict[str, Any] = {
        "fx": fx,
        "taxonomy": taxonomy,
        "period_end": inputs.period_end,
        "aggregated": inputs.aggregated,
    }
    if inputs.category_map is not None:
        category_map = _with_columns(
            _read_csv(inputs.category_map), CATEGORY_MAP_COLUMNS, "category_map"
        )
        prepared = prepare(acq, tgt, category_map=category_map, **kwargs)
        return prepared, {"source": "supplied", "mappings": len(category_map)}
    unmapped = prepare(acq, tgt, **kwargs)
    suggestions = suggest_categories(unmapped.lines, taxonomy)
    accepted = suggestions.dropna(subset=["l2_code"])
    category_map = accepted[list(CATEGORY_MAP_COLUMNS)].reset_index(drop=True)
    prepared = prepare(acq, tgt, category_map=category_map, **kwargs)
    info = {
        "source": "suggested",
        "mappings": len(category_map),
        "native_categories": len(suggestions),
    }
    return prepared, info


def match_lines(
    lines: pd.DataFrame,
    *,
    vendor_parents: pd.DataFrame | None,
    thresholds: Thresholds,
    decisions: pd.DataFrame | None = None,
    vendor_pairs: pd.DataFrame | None = None,
    item_pairs: pd.DataFrame | None = None,
) -> Matching:
    """Vendor and item matching on prepared ``lines``.

    With ``vendor_pairs`` / ``item_pairs`` (the pair logs of an earlier run)
    pair scoring is skipped and only clustering and assembly re-run (PRD 4.5).
    """
    vendor_records = build_vendor_records(lines)
    vendors = match_vendors(
        vendor_records,
        vendor_parents,
        auto_threshold=thresholds.vendor_auto,
        review_threshold=thresholds.vendor_review,
        decisions=decisions,
        cached_pairs=vendor_pairs,
    )
    item_records = build_item_records(lines)
    items = match_items(
        item_records,
        auto_cosine=thresholds.item_auto_cosine,
        review_cosine=thresholds.item_review_cosine,
        decisions=decisions,
        cached_pairs=item_pairs,
    )
    return Matching(vendor_records, item_records, vendors, items)


# --------------------------------------------------------------------------- assembly


def _annotate_lines(lines: pd.DataFrame, matching: Matching) -> pd.DataFrame:
    """Add ``legal_entity_id``, ``parent_id`` and ``canonical_item_id`` to ``lines``."""
    vendor_map = matching.vendors.vendor_map.set_index("vendor_key")
    item_map = matching.items.item_map.set_index("item_record_id")
    out = lines.copy()
    out["legal_entity_id"] = out["vendor_key"].map(vendor_map["legal_entity_id"])
    out["parent_id"] = out["vendor_key"].map(vendor_map["parent_id"])
    record_id = out["company"] + ":" + out["item_key"].astype(object).fillna("")
    canonical = record_id.map(item_map["canonical_item_id"])
    out["canonical_item_id"] = canonical.astype(object).where(canonical.notna(), None)
    return out


def _queue_part(pairs: pd.DataFrame, records: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
    if pairs.empty:
        return pd.DataFrame(columns=list(REVIEW_QUEUE_COLUMNS))
    undecided = pairs.loc[pairs["status"].isin(_UNDECIDED)]
    by_key = records.set_index(key)
    out = undecided[["pair_id", "type", "key_a", "key_b", "score", "stage", "tier"]].copy()
    out["status"] = undecided["status"]
    out["evidence"] = undecided["evidence"]
    for side in ("a", "b"):
        keys = undecided[f"key_{side}"]
        out[f"label_{side}"] = keys.map(by_key[label])
        out[f"spend_{side}"] = keys.map(by_key["spend"]).astype(float).fillna(0.0)
    out["dollars_at_stake"] = out["spend_a"] + out["spend_b"]
    return out[list(REVIEW_QUEUE_COLUMNS)]


def _review_queue(matching: Matching) -> pd.DataFrame:
    """Undecided vendor and item candidates, largest annual spend at stake first."""
    parts = [
        _queue_part(matching.vendors.pairs, matching.vendor_records, "vendor_key", "vendor_name"),
        _queue_part(matching.items.pairs, matching.item_records, "item_record_id", "description"),
    ]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame(columns=list(REVIEW_QUEUE_COLUMNS))
    queue = pd.concat(parts, ignore_index=True)
    return queue.sort_values(
        ["dollars_at_stake", "pair_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)


def _counts(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.fillna("none").value_counts().sort_index().items()}


def _matching_meta(lines: pd.DataFrame, matching: Matching, queue: pd.DataFrame) -> dict[str, Any]:
    """Staged counts for the "Matching in progress" state (PRD 6.13) and tallies."""
    vendor_map = matching.vendors.vendor_map
    item_map = matching.items.item_map
    item_keys = lines.dropna(subset=["item_key"])[["company", "item_key"]].drop_duplicates()
    return {
        "vendors": {
            "records": int(len(vendor_map)),
            "after_normalisation": int(vendor_map["name_normalised"].nunique()),
            "legal_entities": int(vendor_map["legal_entity_id"].nunique()),
            "parents": int(vendor_map["parent_id"].nunique()),
            "by_stage": _counts(vendor_map["stage"]),
            "by_tier": _counts(vendor_map["tier"]),
            "pending_review": int(queue["type"].str.startswith("vendor_").sum()),
        },
        "items": {
            "records": int(len(item_keys)),
            "matchable_records": int(len(item_map)),
            "canonical_items": int(item_map["canonical_item_id"].nunique()),
            "by_stage": _counts(item_map["stage"]),
            "by_tier": _counts(item_map["tier"]),
            "pending_review": int((queue["type"] == "item_match").sum()),
        },
    }


def run_pipeline(
    inputs: PipelineInputs,
    assumptions: Mapping[str, Any] | None = None,
    decisions: pd.DataFrame | None = None,
) -> Results:
    """Run the engine on two purchasing files and return the ``Results``.

    ``assumptions`` and ``decisions``, when given, take the place of the ones in
    ``inputs``. Raises :class:`tieout.ingest.BlockingValidationError` (carrying the
    validation report) when a blocking rule fires.
    """
    taxonomy = load_taxonomy()
    thresholds = inputs.thresholds or load_thresholds()
    merged = _assumptions(inputs, assumptions)
    log = validate_decisions(decisions) if decisions is not None else _decisions(inputs.decisions)
    parents = (
        _with_columns(
            _read_csv(inputs.vendor_parents), PARENT_COLUMNS, "vendor_parents", ("country",)
        )
        if inputs.vendor_parents is not None
        else pd.DataFrame(columns=list(PARENT_COLUMNS))
    )

    acq = _load(inputs.acquirer, "acquirer", inputs.mapping)
    tgt = _load(inputs.target, "target", inputs.mapping)
    prepared, category_info = _prepare(inputs, acq, tgt, taxonomy)
    matching = match_lines(
        prepared.lines, vendor_parents=parents, thresholds=thresholds, decisions=log
    )
    # SYNERGY SEAM (PRD 5, next milestone): levers, bridge, risk guardrails, phasing
    # and prioritisation run here on the annotated lines, the two maps and
    # ``merged``, and fill price_groups, bridge_detail, opportunities,
    # category_risk, payment_terms, phasing, totals and trace. Until then those
    # stay empty; nothing is estimated in their place.

    lines = _annotate_lines(prepared.lines, matching)
    queue = _review_queue(matching)
    meta = {
        **prepared.meta,
        "scenario": inputs.scenario,
        "seed": inputs.seed,
        "view": inputs.view,
        "report_date": inputs.as_of or dt.date.today().isoformat(),
        "category_mapping": category_info,
        "inputs": {
            "vendor_parents": inputs.vendor_parents is not None,
            "fx": "supplied" if inputs.fx is not None else "shipped (illustrative)",
            "category_settings": inputs.category_settings is not None,
            "review_decisions": int(len(log)),
        },
        "thresholds": {
            "vendor_auto": thresholds.vendor_auto,
            "vendor_review": thresholds.vendor_review,
            "item_auto_cosine": thresholds.item_auto_cosine,
            "item_review_cosine": thresholds.item_review_cosine,
        },
        "matching": _matching_meta(lines, matching, queue),
        "stages_run": list(STAGES_RUN),
    }
    return Results(
        meta=meta,
        assumptions=merged,
        lines=lines,
        vendor_map=matching.vendors.vendor_map,
        item_map=matching.items.item_map,
        review_queue=queue,
        review_log=log,
        data_quality=prepared.data_quality,
        vendor_pairs=matching.vendors.pairs,
        item_pairs=matching.items.pairs,
        vendor_parents=parents,
    )
