"""Category mapping onto the common taxonomy (PRD 3.4 and 2.3).

``apply_category_map`` adds the taxonomy attributes to ``lines``;
``suggest_categories`` proposes a mapping for the user to edit;
``unmapped_spend`` reports spend whose category is not mapped.
"""

from __future__ import annotations

import re

import pandas as pd

__all__ = [
    "ATTRIBUTE_COLUMNS",
    "SUGGEST_THRESHOLD",
    "TOP_DESCRIPTIONS",
    "apply_category_map",
    "none_for_missing",
    "suggest_categories",
    "tokenize",
    "unmapped_spend",
]

SUGGEST_THRESHOLD = 0.3
TOP_DESCRIPTIONS = 20
ATTRIBUTE_COLUMNS = ("l1_code", "l2_code", "family", "uom_dimension", "category_type")
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: object) -> set[str]:
    """Lower-case alphanumeric tokens of ``text`` (empty for non-strings)."""
    return set(_TOKEN.findall(text.lower())) if isinstance(text, str) else set()


def _key(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.casefold().astype(object)


def apply_category_map(
    lines: pd.DataFrame, category_map: pd.DataFrame | None, taxonomy: pd.DataFrame
) -> pd.DataFrame:
    """Add ``l1_code``, ``l2_code``, ``family``, ``uom_dimension`` and ``category_type``.

    ``category_map`` has ``company``, ``category_native`` and ``l2_code``;
    native labels match after trimming and case-folding. Unmapped lines, and
    lines mapped to a code that is not in ``taxonomy``, get ``None`` in all
    five columns. When a (company, label) pair is listed twice the last row wins.
    """
    out = lines.copy()
    known = taxonomy.set_index("l2_code")
    if category_map is None or category_map.empty:
        l2 = pd.Series([None] * len(out), index=out.index, dtype=object)
    else:
        table = category_map.assign(_key=_key(category_map["category_native"]))
        table = table.drop_duplicates(["company", "_key"], keep="last")
        pairs = pd.MultiIndex.from_frame(
            pd.DataFrame({"company": table["company"], "key": table["_key"]})
        )
        codes = pd.Series(table["l2_code"].to_numpy(dtype=object), index=pairs)
        wanted = pd.MultiIndex.from_arrays([out["company"], _key(out["category_native"])])
        l2 = pd.Series(codes.reindex(wanted).to_numpy(dtype=object), index=out.index)
        l2 = l2.where(l2.isin(known.index))
    out["l2_code"] = none_for_missing(l2)
    for column in ("l1_code", "family", "uom_dimension", "category_type"):
        values = out["l2_code"].map(known[column].to_dict())
        out[column] = none_for_missing(values.where(out["l2_code"].notna()))
    return out


def suggest_categories(
    lines: pd.DataFrame,
    taxonomy: pd.DataFrame,
    *,
    threshold: float = SUGGEST_THRESHOLD,
    top_descriptions: int = TOP_DESCRIPTIONS,
) -> pd.DataFrame:
    """Suggest an L2 code for each native category (PRD 2.3).

    The score is the Jaccard overlap between an L2's keyword set and the tokens
    of the native label plus its ``top_descriptions`` highest-spend item
    descriptions. The top L2 is suggested when its score is at least
    ``threshold``; otherwise ``l2_code`` is ``None``. Ties break on ``l2_code``.

    Returns ``company``, ``category_native``, ``spend``, ``l2_code``,
    ``l2_name`` and ``score``, sorted by company and descending spend.
    """
    keywords = {
        row.l2_code: tokenize(row.keywords.replace(";", " ")) for row in taxonomy.itertuples()
    }
    names = taxonomy.set_index("l2_code")["l2_name"].to_dict()
    spend_col = "amount" if "amount" in lines else "line_amount"
    frame = lines[["company", "category_native", "item_description", spend_col]].rename(
        columns={spend_col: "spend"}
    )
    frame = frame.dropna(subset=["category_native"])

    totals = frame.groupby(["company", "category_native"], sort=True)["spend"].sum()
    by_description = (
        frame.dropna(subset=["item_description"])
        .groupby(["company", "category_native", "item_description"], sort=True)["spend"]
        .sum()
        .reset_index()
        .sort_values(
            ["company", "category_native", "spend", "item_description"],
            ascending=[True, True, False, True],
            kind="stable",
        )
        .groupby(["company", "category_native"], sort=True)
        .head(top_descriptions)
    )
    descriptions = by_description.groupby(["company", "category_native"], sort=True)[
        "item_description"
    ].apply(list)

    rows = []
    for (company, label), spend in totals.items():
        tokens = tokenize(label)
        for description in descriptions.get((company, label), []):
            tokens |= tokenize(description)
        scores = {
            code: len(words & tokens) / len(words | tokens) if (words | tokens) else 0.0
            for code, words in keywords.items()
        }
        best = min(scores, key=lambda code: (-scores[code], code))
        hit = scores[best] >= threshold
        rows.append(
            {
                "company": company,
                "category_native": label,
                "spend": float(spend),
                "l2_code": best if hit else None,
                "l2_name": names[best] if hit else None,
                "score": float(scores[best]),
            }
        )
    out = pd.DataFrame(
        rows, columns=["company", "category_native", "spend", "l2_code", "l2_name", "score"]
    )
    return out.sort_values(
        ["company", "spend", "category_native"], ascending=[True, False, True], kind="stable"
    ).reset_index(drop=True)


def unmapped_spend(lines: pd.DataFrame) -> pd.DataFrame:
    """Spend in unmapped categories, by company and native label.

    Returns ``company``, ``category_native``, ``rows``, ``amount`` and ``share``
    (of that company's in-scope spend), largest first.
    """
    total = lines.groupby("company")["amount"].sum()
    unmapped = lines[lines["l2_code"].isna()]
    grouped = (
        unmapped.assign(category_native=unmapped["category_native"].fillna("(blank)"))
        .groupby(["company", "category_native"], sort=True)["amount"]
        .agg(rows="size", amount="sum")
        .reset_index()
    )
    denominator = grouped["company"].map(total).astype(float)
    grouped["share"] = (grouped["amount"] / denominator).where(denominator != 0, 0.0)
    return grouped.sort_values(
        ["company", "amount", "category_native"], ascending=[True, False, True], kind="stable"
    ).reset_index(drop=True)


def none_for_missing(series: pd.Series) -> pd.Series:
    """``series`` as object dtype with ``None`` (not NaN) for missing values."""
    out = series.astype(object)
    out[out.isna().to_numpy(dtype=bool)] = None
    return out
