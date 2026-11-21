"""The bridge (signature moment 1, PRD 6.2): chart, table, caption and bar drill-down.

Shared by Overview and Synergies. Selecting a removal step lists what it
refused to count (``refused_items``); selecting a total opens its working.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from components import state
from components.plotting import bridge_figure, chart_with_table, exact_money, selected_row
from components.style import esc
from components.trace import render_trace
from tieout.views import bridge, money, money_range, refused_items, thousands

__all__ = ["bridge_caption", "render_bar_detail", "render_bridge", "render_refused"]


def _hover(frame: pd.DataFrame) -> list[str]:
    """Exact figure and the count of items behind each bar (PRD 6.8)."""
    out = []
    for label, amount, items in zip(frame["label"], frame["amount"], frame["items"], strict=True):
        count = f"<br>{items:,} items" if items else ""
        out.append(f"{label}<br>{exact_money(amount)}{count}")
    return out


def _table(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Bar": frame["label"],
            "Amount": frame["text"],
            "Items": [int(i) if i else None for i in frame["items"]],
        }
    )


def bridge_caption(frame: pd.DataFrame) -> str:
    """One sentence under the chart: where it starts, ends and the largest removal."""
    steps = frame[frame["kind"] == "decrease"]
    final = frame.iloc[-1]
    sentence = (
        f"The naive figure of {money(frame.iloc[0]['amount'])} falls to a defensible "
        f"{money_range(final['low'], final['high'])} run-rate saving"
    )
    if not steps.empty:
        largest = steps.loc[steps["amount"].idxmin()]
        sentence += (
            f"; the largest removal is {largest['label'].lower()} ({thousands(-largest['amount'])})"
        )
    return sentence + ". Select a bar to see what it is made of."


def render_bridge(key: str, *, height: int = 440) -> Mapping[str, Any] | None:
    """The bridge chart with its table toggle and caption; returns the selected bar's row."""
    frame = bridge(state.current_results(), state.view())
    fig = bridge_figure(frame, hover=_hover(frame), height=height)
    index = chart_with_table(fig, _table(frame), key, bridge_caption(frame), shape="main")
    if index is None or index >= len(frame):
        return None
    return frame.iloc[index].to_dict()


def render_refused(step: int, key: str) -> None:
    """The filterable list of what bridge step ``step`` removed, each item openable (clean)."""
    mode = state.view()
    frame = refused_items(state.current_results(), step, mode)
    if frame.empty:
        st.info("This step removed nothing.")
        return
    categories = sorted(frame["category"].unique())
    chosen = st.multiselect(
        "Filter by category", categories, key=f"{key}_filter_{step}", placeholder="All categories"
    )
    shown = frame[frame["category"].isin(chosen)] if chosen else frame
    if mode == "masked":
        table = pd.DataFrame(
            {"Category": shown["category"], "Items": shown["items"], "Removed": shown["text"]}
        )
    else:
        table = pd.DataFrame(
            {
                "Item": shown["item"],
                "Category": shown["category"],
                "Buying groups": shown["groups"],
                "Naive gap": [thousands(v) for v in shown["naive_gap"]],
                "Removed": shown["text"],
                "Why": shown["reason"],
            }
        )
    event = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        on_select="rerun" if mode != "masked" else "ignore",
        selection_mode="single-row",
        key=f"{key}_list_{step}",
    )
    st.caption(
        f"{len(shown):,} of {len(frame):,} rows."
        + ("" if mode == "masked" else " Select an item to see its working.")
    )
    index = selected_row(event) if mode != "masked" else None
    if index is not None and index < len(shown):
        row = shown.iloc[index]
        render_trace(str(row["figure_id"]), f"{key}_item", measure=str(row["measure"]))


def render_bar_detail(bar: Mapping[str, Any], key: str) -> None:
    """Under a selected bridge bar: a removal step's refused list, or a total's working."""
    with st.container(border=True):
        st.markdown(f"**{esc(bar['label'])}**: {esc(bar['text'])}")
        if bar["kind"] == "decrease":
            render_refused(int(bar["step"]), key)
        else:
            render_trace(str(bar["figure_id"]), f"{key}_trace")
