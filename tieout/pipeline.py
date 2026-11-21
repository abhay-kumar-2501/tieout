"""The engine pipeline: load, prepare, match, size the synergies, assemble ``Results``.

``run_pipeline`` is the single entry point every surface uses (PRD 9.2)::

    load -> prepare -> vendor matching -> item matching -> synergy -> Results

Matching is expensive; the arithmetic is not. Two cheaper entry points reuse
a ``Results``:

- :func:`recompute` re-runs only the synergy arithmetic for new assumptions
  (PRD 6.7, under half a second on the demo data);
- :func:`apply_decisions` re-runs clustering and one-to-one assembly from the
  cached pair scores, then the arithmetic (PRD 4.5: no rescoring, under two
  seconds on the demo data).
"""

from __future__ import annotations

import datetime as dt
import io
import json
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
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
from tieout.synergy import SynergyOutputs, evaluate
from tieout.synergy.settings import CASES

__all__ = [
    "MATCH_QUEUE_TYPES",
    "REVIEW_QUEUE_COLUMNS",
    "Matching",
    "PipelineInputs",
    "apply_decisions",
    "match_lines",
    "read_category_settings",
    "recompute",
    "rematch",
    "run_pipeline",
    "thresholds_of",
]

PathLike = str | Path
Table = pd.DataFrame | PathLike
ColumnMapping = Mapping[str, str] | Mapping[str, Mapping[str, str]]

COMPANIES = ("acquirer", "target")
PARENT_COLUMNS = ("key_type", "key", "country", "parent_name")
CATEGORY_MAP_COLUMNS = ("company", "category_native", "l2_code")
#: Queue types raised by matching; ``unit_flag`` and ``incoterm`` come from lever 1.
MATCH_QUEUE_TYPES = ("vendor_match", "vendor_sibling", "item_match")
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
    "canonical_item_id",
    "message",
    "ratio",
    "factor",
    "stake",
)
_QUEUE_NUMBERS = ("score", "spend_a", "spend_b", "dollars_at_stake", "ratio", "factor", "stake")
_UNDECIDED = ("pending", "deferred")
STAGES_RUN = ("ingest", "vendor_matching", "item_matching", "synergy")
_SETTING_TRIPLES = ("pi1_same", "pi1_switch", "pi2")


@dataclass(frozen=True)
class PipelineInputs:
    """Everything one run reads. Files may be given as paths or as frames.

    ``acquirer`` and ``target`` are purchasing files (PRD 3.1) or raw frames with
    the schema column names. ``mapping`` maps file headers to schema names,
    either one mapping for both files or ``{"acquirer": {...}, "target": {...}}``.
    Without ``category_map`` the top category suggestion scoring at least 0.3 is
    accepted (PRD 9.2). ``assumptions`` overrides the defaults (a mapping or a
    TOML file); ``category_settings`` is the per-category settings file (PRD
    3.2), stored as ``assumptions["category_settings"]``; ``decisions`` is a
    review decisions log (PRD 4.5). ``scorecard`` and ``sensitivity`` are the
    evaluation's JSON outputs (PRD 4.7), read as optional inputs and carried on
    the ``Results`` unchanged.
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
    reporting_currency: str = "USD"
    view: str = "clean"
    thresholds: Thresholds | None = None
    scenario: str = "custom"
    seed: int | None = None
    scorecard: Mapping[str, Any] | PathLike | None = None
    sensitivity: Mapping[str, Any] | PathLike | None = None


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


def _cell(value: object) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def read_category_settings(source: Table) -> dict[str, dict[str, Any]]:
    """``category_settings.csv`` (PRD 3.2) as ``l2_code`` -> non-blank cells.

    ``criticality`` stays text; every other cell is a number that must lie in
    [0, 1], and the cells given of each probability triple must satisfy
    low <= base <= high (PRD 5.1). Raises ``ValueError`` otherwise.
    """
    frame = _read_csv(source)
    if "l2_code" not in frame.columns:
        raise ValueError("category_settings: missing column 'l2_code'")
    table: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict("records"):
        l2 = _cell(row.pop("l2_code"))
        if l2 is None:
            continue
        cells: dict[str, Any] = {}
        for column, value in row.items():
            text = _cell(value)
            if text is None:
                continue
            if column == "criticality":
                cells[column] = text
                continue
            number = float(text)
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"category_settings {l2}.{column} must lie in [0, 1]: {text}")
            cells[column] = number
        for prefix in _SETTING_TRIPLES:
            given = [cells[f"{prefix}_{c}"] for c in CASES if f"{prefix}_{c}" in cells]
            if given != sorted(given):
                raise ValueError(f"category_settings {l2}.{prefix} needs low <= base <= high")
        table[l2] = cells
    return table


def _json_input(source: Mapping[str, Any] | PathLike | None) -> dict[str, Any] | None:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return dict(source)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _assumptions(inputs: PipelineInputs, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """Defaults, then the category settings file, then the overrides (PRD 5.1 lookup order)."""
    given: Mapping[str, Any] | None
    if overrides is not None:
        given = overrides
    elif isinstance(inputs.assumptions, str | Path):
        given = tomllib.loads(Path(inputs.assumptions).read_text(encoding="utf-8"))
    else:
        given = inputs.assumptions
    base: dict[str, Any] = {}
    if inputs.category_settings is not None:
        base["category_settings"] = read_category_settings(inputs.category_settings)
    merged = merge_overrides(given, merge_overrides(base))
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
        "reporting_currency": inputs.reporting_currency,
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


def thresholds_of(results: Results) -> Thresholds:
    """The matching thresholds a ``Results`` was produced with."""
    return Thresholds(**results.meta["thresholds"])


# --------------------------------------------------------------------------- assembly


def _annotate_lines(
    lines: pd.DataFrame, vendor_map: pd.DataFrame, item_map: pd.DataFrame
) -> pd.DataFrame:
    """Add (or replace) ``legal_entity_id``, ``parent_id`` and ``canonical_item_id``."""
    vendors = vendor_map.set_index("vendor_key")
    items = item_map.set_index("item_record_id")
    out = lines.copy()
    out["legal_entity_id"] = out["vendor_key"].map(vendors["legal_entity_id"])
    out["parent_id"] = out["vendor_key"].map(vendors["parent_id"])
    record_id = out["company"] + ":" + out["item_key"].astype(object).fillna("")
    canonical = record_id.map(items["canonical_item_id"])
    out["canonical_item_id"] = canonical.astype(object).where(canonical.notna(), None)
    return out


def _labelled_maps(matching: Matching) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The two maps with each record's annual spend (and the item description) attached."""
    vendor_spend = matching.vendor_records.set_index("vendor_key")["spend"]
    vendor_map = matching.vendors.vendor_map.copy()
    vendor_map["spend"] = vendor_map["vendor_key"].map(vendor_spend).astype(float).fillna(0.0)
    records = matching.item_records.set_index("item_record_id")
    item_map = matching.items.item_map.copy()
    item_map["description"] = item_map["item_record_id"].map(records["description"]).astype(object)
    item_map["spend"] = item_map["item_record_id"].map(records["spend"]).astype(float).fillna(0.0)
    return vendor_map, item_map


def _queue_part(
    pairs: pd.DataFrame, labels: pd.Series, spend: pd.Series, columns: list[str]
) -> pd.DataFrame:
    undecided = pairs.loc[pairs["status"].isin(_UNDECIDED), columns].copy()
    for side in ("a", "b"):
        keys = undecided[f"key_{side}"]
        undecided[f"label_{side}"] = keys.map(labels).astype(object)
        undecided[f"spend_{side}"] = keys.map(spend).astype(float).fillna(0.0)
    undecided["dollars_at_stake"] = undecided["spend_a"] + undecided["spend_b"]
    return undecided.reindex(columns=list(REVIEW_QUEUE_COLUMNS))


def _sorted_queue(parts: list[pd.DataFrame]) -> pd.DataFrame:
    present = [p for p in parts if not p.empty]
    if not present:
        return pd.DataFrame(columns=list(REVIEW_QUEUE_COLUMNS))
    queue = pd.concat(present, ignore_index=True)
    for column in REVIEW_QUEUE_COLUMNS:
        values = queue[column]
        if column in _QUEUE_NUMBERS:
            queue[column] = values.astype(float)
        else:  # text: blanks are None, whichever part the row came from
            queue[column] = values.astype(object).where(values.notna(), None)
    return queue.sort_values(
        ["dollars_at_stake", "pair_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)


def _match_queue(
    vendor_pairs: pd.DataFrame,
    item_pairs: pd.DataFrame,
    vendor_map: pd.DataFrame,
    item_map: pd.DataFrame,
) -> pd.DataFrame:
    """Undecided vendor and item candidates, largest annual spend at stake first."""
    columns = ["pair_id", "type", "key_a", "key_b", "score", "stage", "tier", "status", "evidence"]
    vendors = vendor_map.set_index("vendor_key")
    items = item_map.set_index("item_record_id")
    parts = []
    if not vendor_pairs.empty:
        parts.append(_queue_part(vendor_pairs, vendors["vendor_name"], vendors["spend"], columns))
    if not item_pairs.empty:
        parts.append(_queue_part(item_pairs, items["description"], items["spend"], columns))
    return _sorted_queue(parts)


def _review_queue(
    queue: pd.DataFrame, outputs: SynergyOutputs, item_map: pd.DataFrame
) -> pd.DataFrame:
    """The matching queue with each item candidate's stake, plus lever 1's review items.

    ``stake`` is the lever-1 gross gap approval would add (PRD 6.5): for a tier C
    item candidate, the would-be gap of its pending opportunities; for a
    ``unit_flag`` or ``incoterm`` item, the gap with the flag cleared. Vendor
    candidates carry no stake.
    """
    matched = queue.loc[queue["type"].isin(MATCH_QUEUE_TYPES)].copy()
    opps = outputs.opportunities
    pending = opps.loc[opps["status"] == "pending_review"]
    would_be = (
        pending.groupby(["record_acquirer", "record_target"], as_index=False)["gross_gap"]
        .sum()
        .rename(columns={"record_acquirer": "key_a", "record_target": "key_b"})
    )
    stake = matched[["key_a", "key_b"]].merge(would_be, on=["key_a", "key_b"], how="left")
    matched["stake"] = np.where(
        matched["type"] == "item_match", stake["gross_gap"].to_numpy(dtype=float), np.nan
    )

    items = outputs.review_items
    flagged = items.loc[items["status"].isin(_UNDECIDED)].copy()
    records = item_map.set_index("item_record_id")
    for side in ("a", "b"):
        keys = flagged[f"key_{side}"]
        flagged[f"label_{side}"] = keys.map(records["description"]).astype(object)
        flagged[f"spend_{side}"] = keys.map(records["spend"]).astype(float).fillna(0.0)
    flagged["dollars_at_stake"] = flagged["spend_a"] + flagged["spend_b"]
    flagged["evidence"] = flagged["message"]
    flagged = flagged.reindex(columns=list(REVIEW_QUEUE_COLUMNS))
    return _sorted_queue([matched.reindex(columns=list(REVIEW_QUEUE_COLUMNS)), flagged])


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


def _with_matching(results: Results, matching: Matching, log: pd.DataFrame) -> Results:
    """``results`` with a new matching outcome: ids on the lines, maps, pair logs and queue.

    The synergy outputs are left as they were; :func:`recompute` refreshes them.
    """
    vendor_map, item_map = _labelled_maps(matching)
    lines = _annotate_lines(results.lines, vendor_map, item_map)
    queue = _match_queue(matching.vendors.pairs, matching.items.pairs, vendor_map, item_map)
    meta = {
        **results.meta,
        "inputs": {**results.meta["inputs"], "review_decisions": int(len(log))},
        "matching": _matching_meta(lines, matching, queue),
    }
    return replace(
        results,
        meta=meta,
        lines=lines,
        vendor_map=vendor_map,
        item_map=item_map,
        review_queue=queue,
        review_log=log,
        vendor_pairs=matching.vendors.pairs,
        item_pairs=matching.items.pairs,
        synergy_cache=None,
    )


def _switched_off(results: Results, totals: Mapping[str, Any]) -> dict[str, str]:
    """Features that are off for this run, each with what would switch it on (PRD 6.13)."""
    checks = totals["checks"]
    features = results.meta.get("features", {})
    off: dict[str, str] = {}
    if not checks["contract_lock_in_assessed"]:
        off["contract_lock_in"] = (
            "Contract lock-in was not assessed: add contract end dates (and a close date for "
            "aggregated data) to enable bridge step 6."
        )
    if totals["phasing"]["method"] != "contract":
        off["contract_phasing"] = "Add contract end dates to enable contract-aware phasing."
    if not checks["lever3_enabled"]:
        off["lever3"] = str(checks["lever3_message"])
    if not features.get("observed_days_to_pay", False):
        off["observed_days_to_pay"] = (
            "Add payment dates to use observed days-to-pay; stated terms are used instead."
        )
    if not checks["benchmark_line_test"]:
        off["benchmark_line_test"] = (
            "The three-line benchmark test is skipped because the data is aggregated."
        )
    if not bool(results.lines["incoterm"].notna().any()):
        off["incoterms"] = "Add incoterms to test for non-comparable delivery terms (step 5)."
    if results.scorecard is None:
        off["scorecard"] = "The accuracy scorecard needs hidden truth; it is shown for demo data."
    if results.sensitivity is None:
        off["sensitivity"] = "Threshold sensitivity is precomputed for the demo data only."
    return off


def recompute(results: Results, assumptions: Mapping[str, Any] | None) -> Results:
    """Re-run only the synergy arithmetic for ``assumptions`` (PRD 6.7).

    ``assumptions`` are merged over the defaults, as in :func:`run_pipeline`;
    pass an edited copy of ``results.assumptions`` to keep the run's category
    settings. Matching, the pair logs and the lines are reused as they are.
    """
    settings = merge_overrides(assumptions)
    validate(settings)
    cache = results.cached_synergy()
    outputs = evaluate(cache, settings)
    trace = outputs.trace
    updated = replace(
        results,
        assumptions=settings,
        review_queue=_review_queue(results.review_queue, outputs, results.item_map),
        price_groups=outputs.price_groups,
        bridge_detail=outputs.bridge_detail,
        opportunities=outputs.opportunities,
        internal_variance=outputs.internal_variance,
        category_risk=outputs.category_risk,
        payment_terms=outputs.payment_terms,
        phasing=outputs.phasing,
        totals=outputs.totals,
        trace=trace.children,
        trace_amounts=trace.line_amounts,
        trace_figures=trace.figures,
        synergy_cache=cache,
    )
    meta = {**results.meta, "switched_off": _switched_off(updated, outputs.totals)}
    return replace(updated, meta=meta)


def _reassemble(results: Results, log: pd.DataFrame, thresholds: Thresholds) -> Results:
    """Clustering and one-to-one assembly from the cached pair scores, then the arithmetic."""
    matching = match_lines(
        results.lines,
        vendor_parents=results.vendor_parents,
        thresholds=thresholds,
        decisions=log,
        vendor_pairs=results.vendor_pairs,
        item_pairs=results.item_pairs,
    )
    reassembled = _with_matching(results, matching, log)
    meta = {**reassembled.meta, "thresholds": asdict(thresholds)}
    return recompute(replace(reassembled, meta=meta), results.assumptions)


def apply_decisions(results: Results, decisions: pd.DataFrame | None) -> Results:
    """Apply a review decisions log, then re-run the arithmetic (PRD 4.5).

    ``decisions`` is the complete log (it replaces ``results.review_log``), so
    undo is a log without its last row. Clustering and one-to-one assembly
    re-run from the cached pair scores in ``vendor_pairs`` and ``item_pairs``;
    no pair is rescored.
    """
    return _reassemble(results, validate_decisions(decisions), thresholds_of(results))


def rematch(results: Results, thresholds: Thresholds) -> Results:
    """Re-run assembly and the arithmetic with other automatic thresholds (PRD 4.7 sensitivity).

    Pairs are not rescored, so a review threshold below the one the pairs were
    scored with cannot bring back pairs that were never kept.
    """
    return _reassemble(results, results.review_log, thresholds)


def run_pipeline(
    inputs: PipelineInputs,
    assumptions: Mapping[str, Any] | None = None,
    decisions: pd.DataFrame | None = None,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Results:
    """Run the engine on two purchasing files and return the ``Results``.

    ``progress``, when given, is called as ``progress(stage, counts)`` after each
    stage with real counts (stages ``ingest``, ``vendor_matching``,
    ``item_matching``, ``synergy``) so a screen can show staged progress (PRD 6.13).

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

    def report(stage: str, counts: Mapping[str, Any]) -> None:
        if progress is not None:
            progress(stage, counts)

    report(
        "ingest",
        {
            "rows": {"acquirer": len(acq), "target": len(tgt)},
            "lines": len(prepared.lines),
            "vendor_records": int(prepared.lines["vendor_key"].nunique()),
        },
    )
    matching = match_lines(
        prepared.lines, vendor_parents=parents, thresholds=thresholds, decisions=log
    )
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
        "stages_run": list(STAGES_RUN),
    }
    unmatched = Results(
        meta=meta,
        assumptions=merged,
        lines=prepared.lines,
        data_quality=prepared.data_quality,
        vendor_parents=parents,
        scorecard=_json_input(inputs.scorecard),
        sensitivity=_json_input(inputs.sensitivity),
    )
    matched = _with_matching(unmatched, matching, log)
    report("vendor_matching", matched.meta["matching"]["vendors"])
    report("item_matching", matched.meta["matching"]["items"])
    final = recompute(matched, merged)
    report("synergy", {"totals": True})
    return final
