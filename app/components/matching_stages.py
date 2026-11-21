"""How two vendor lists and two item lists became one (PRD 6.3, 6.13): counts by tier.

Draws ``matching_counts`` as it is; stage names are plain-language labels only.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.plotting import chart_with_table, themed
from components.style import esc
from tieout import theme as t

_VENDOR_STAGES = {
    "V1": "Same tax ID",
    "V2": "Same normalised name",
    "V3": "Parent table",
    "V4": "Fuzzy name, automatic",
    "none": "Not matched",
}
_ITEM_STAGES = {
    "I1": "Same manufacturer part number",
    "I2": "Same critical attributes",
    "I3": "Text similarity with corroboration",
    "none": "Not matched",
}
_TIER_LABEL = {
    "A": "Tier A: deterministic",
    "B": "Tier B: automatic on similarity",
    "none": "Not matched",
}
_TIER_COLOR = {"A": t.TEAL, "B": t.ACQUIRER, "none": t.BORDER}


def _tier_figure(counts: dict[str, Any]) -> tuple[go.Figure, pd.DataFrame]:
    rows = [
        {
            "kind": "Vendor records" if kind == "vendors" else "Item records",
            "tier": tier,
            "count": int(counts[kind]["by_tier"].get(tier, 0)),
        }
        for kind in ("vendors", "items")
        for tier in ("A", "B", "none")
    ]
    frame = pd.DataFrame(rows)
    fig = go.Figure()
    for tier in ("A", "B", "none"):
        part = frame[frame["tier"] == tier]
        fig.add_bar(
            y=part["kind"],
            x=part["count"],
            orientation="h",
            name=_TIER_LABEL[tier],
            marker={"color": _TIER_COLOR[tier]},
            hovertemplate="%{y}: %{x:,} records<extra>" + _TIER_LABEL[tier] + "</extra>",
        )
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Records")
    fig.update_yaxes(autorange="reversed")
    fig = themed(fig, height=210, legend=True)
    table = frame.assign(tier=frame["tier"].map(_TIER_LABEL)).rename(
        columns={"kind": "List", "tier": "Tier", "count": "Records"}
    )
    return fig, table


def render_stages(counts: dict[str, Any]) -> None:
    """Both stage sentences, the tier chart (with its table) and the per-stage counts."""
    vendors, items = counts["vendors"], counts["items"]
    st.markdown(
        f"**Vendors:** {esc(vendors['text'])}  \n**Items:** {esc(items['text'])}",
        unsafe_allow_html=True,
    )
    fig, table = _tier_figure(counts)
    caption = (
        f"Of {vendors['records']:,} vendor records, {vendors['by_tier'].get('A', 0):,} matched "
        f"at tier A and {vendors['by_tier'].get('B', 0):,} at tier B; of {items['records']:,} "
        f"item records, {items['by_tier'].get('A', 0):,} and {items['by_tier'].get('B', 0):,}. "
        f"Tier C candidates wait for review: {vendors['pending_review']:,} vendor and "
        f"{items['pending_review']:,} item pairs."
    )
    chart_with_table(fig, table, "mt_tiers", caption)
    left, right = st.columns(2)
    for column, title, data, names in (
        (left, "Vendor records by stage", vendors, _VENDOR_STAGES),
        (right, "Item records by stage", items, _ITEM_STAGES),
    ):
        with column, st.expander(title):
            st.dataframe(
                pd.DataFrame(
                    {
                        "Stage": [names.get(k, k) for k in data["by_stage"]],
                        "Records": list(data["by_stage"].values()),
                    }
                ),
                hide_index=True,
                width="stretch",
            )
