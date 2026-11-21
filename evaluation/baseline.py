"""The naive baseline matcher of PRD 4.7, for side-by-side comparison.

Vendors: `token_set_ratio` >= 85 on lower-cased names over all pairs, clustered by
connected components (so chains merge and token-subset names merge).
Items: word-level `TfidfVectorizer()` cosine >= 0.80 within L2, many-to-many, no
attribute veto, so the result is a pair list rather than a one-to-one map.
Lever 1 then runs on these matches with all bridge filters on (PRD 4.7); for
that, `baseline_item_map` keeps each record's single best pair.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer

VENDOR_THRESHOLD = 85.0
ITEM_COSINE_THRESHOLD = 0.80
_EPSILON = 1e-9

VENDOR_MAP_COLUMNS = [
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
]
ITEM_PAIR_COLUMNS = ["item_record_id_a", "item_record_id_b", "l2_code", "score"]
ITEM_MAP_COLUMNS = [
    "item_record_id",
    "company",
    "item_key",
    "canonical_item_id",
    "partner_id",
    "stage",
    "score",
    "tier",
    "l2_code",
]


def baseline_vendor_map(
    vendor_records: pd.DataFrame, threshold: float = VENDOR_THRESHOLD
) -> pd.DataFrame:
    """Cluster vendor records with the naive design; returns a `vendor_map`-shaped frame.

    Input columns: vendor_key, company, vendor_id, vendor_name.
    Clustered records get stage `V4`, tier `B` and the best score against another
    member; singletons get stage `none`, score 0 and tier None. `legal_entity_id`
    follows the ARCHITECTURE rule (LE + integer by sorted smallest member key) and
    `parent_id` equals it (the baseline has no parent table).
    """
    missing = [
        c for c in ("vendor_key", "company", "vendor_id", "vendor_name") if c not in vendor_records
    ]
    if missing:
        raise ValueError(f"vendor_records: missing columns {missing}")
    records = vendor_records.sort_values("vendor_key", kind="stable").reset_index(drop=True)
    names = records["vendor_name"].fillna("").astype(str).str.lower().tolist()
    count = len(records)
    if count:
        scores = process.cdist(
            names, names, scorer=fuzz.token_set_ratio, score_cutoff=threshold, dtype=np.uint8
        )
        np.fill_diagonal(scores, 0)
        _, labels = connected_components(csr_matrix(scores > 0), directed=False)
        best = scores.max(axis=1).astype(float)
    else:
        labels = np.zeros(0, dtype=int)
        best = np.zeros(0)
    # Components are labelled in order of first appearance, i.e. by smallest sorted key.
    sizes = np.bincount(labels) if count else np.zeros(0, dtype=int)
    clustered = sizes[labels] > 1 if count else np.zeros(0, dtype=bool)
    out = pd.DataFrame(
        {
            "vendor_key": records["vendor_key"],
            "company": records["company"],
            "vendor_id": records["vendor_id"],
            "vendor_name": records["vendor_name"],
            "name_normalised": names,
            "legal_entity_id": [f"LE{label + 1:05d}" for label in labels],
            "stage": np.where(clustered, "V4", "none"),
            "score": np.where(clustered, best, 0.0),
            "tier": pd.Series(np.where(clustered, "B", None), dtype=object),
        }
    )
    out["parent_id"] = out["legal_entity_id"]
    return out[VENDOR_MAP_COLUMNS]


def baseline_item_pairs(
    item_records: pd.DataFrame, threshold: float = ITEM_COSINE_THRESHOLD
) -> pd.DataFrame:
    """All cross-company item pairs in the same L2 with TF-IDF cosine >= threshold.

    Input columns: item_record_id, company (acquirer/target), description, l2_code.
    A fresh word-level `TfidfVectorizer()` is fitted per L2 category. Output
    columns: item_record_id_a (acquirer), item_record_id_b (target), l2_code, score;
    sorted by the two ids. Many-to-many: a record may appear in several pairs.
    """
    needed = ["item_record_id", "company", "description", "l2_code"]
    missing = [c for c in needed if c not in item_records]
    if missing:
        raise ValueError(f"item_records: missing columns {missing}")
    frames = []
    for l2_code, group in item_records.sort_values("item_record_id", kind="stable").groupby(
        "l2_code", sort=True
    ):
        acquirer = group[group["company"] == "acquirer"]
        target = group[group["company"] == "target"]
        if acquirer.empty or target.empty:
            continue
        texts = group["description"].fillna("").astype(str).tolist()
        try:
            matrix = TfidfVectorizer().fit_transform(texts)
        except ValueError:  # no usable words in this category
            continue
        similarity = (matrix @ matrix.T).tocsr()
        position = {rid: i for i, rid in enumerate(group["item_record_id"])}
        rows = [position[r] for r in acquirer["item_record_id"]]
        cols = [position[r] for r in target["item_record_id"]]
        block = similarity[rows][:, cols].toarray()
        hit_rows, hit_cols = np.nonzero(block >= threshold - _EPSILON)
        acq_ids = acquirer["item_record_id"].to_numpy()
        tgt_ids = target["item_record_id"].to_numpy()
        frames.append(
            pd.DataFrame(
                {
                    "item_record_id_a": acq_ids[hit_rows],
                    "item_record_id_b": tgt_ids[hit_cols],
                    "l2_code": l2_code,
                    "score": block[hit_rows, hit_cols],
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=ITEM_PAIR_COLUMNS)
    pairs = pd.concat(frames, ignore_index=True)
    return pairs.sort_values(["item_record_id_a", "item_record_id_b"], kind="stable").reset_index(
        drop=True
    )[ITEM_PAIR_COLUMNS]


def baseline_item_map(item_records: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """An `item_map`-shaped frame from the baseline's many-to-many pairs, for lever 1.

    Lever 1 counts each record under one item, so each record keeps only its
    single best pair: pairs are taken greedily by descending score, ties by
    the two record ids (the rule the tool's naive figure applies to its own
    candidates). Paired records share a canonical item at tier B (stage `I3`);
    the rest stay unmatched. Canonical ids follow sorted `item_record_id`.
    """
    records = item_records.sort_values("item_record_id", kind="stable").reset_index(drop=True)
    ids = {rid: f"CI{n:06d}" for n, rid in enumerate(records["item_record_id"], start=1)}
    ranked = pairs.sort_values(
        ["score", "item_record_id_a", "item_record_id_b"],
        ascending=[False, True, True],
        kind="stable",
    )
    partner: dict[str, str] = {}
    score: dict[str, float] = {}
    for a, b, value in zip(
        ranked["item_record_id_a"], ranked["item_record_id_b"], ranked["score"], strict=True
    ):
        if a in partner or b in partner:
            continue
        partner[a], partner[b] = b, a
        score[a] = score[b] = float(value)
    record_ids = records["item_record_id"]
    paired = record_ids.isin(partner)
    out = pd.DataFrame(
        {
            "item_record_id": record_ids,
            "company": records["company"],
            "item_key": records["item_key"],
            "canonical_item_id": [
                min(ids[r], ids[partner[r]]) if r in partner else ids[r] for r in record_ids
            ],
            "partner_id": pd.Series([partner.get(r) for r in record_ids], dtype=object),
            "stage": np.where(paired, "I3", "none"),
            "score": [score.get(r, np.nan) for r in record_ids],
            "tier": pd.Series(np.where(paired, "B", None), dtype=object),
            "l2_code": records["l2_code"],
        }
    )
    return out[ITEM_MAP_COLUMNS]
