"""Synergies (PRD 6.3, 6.8, 5.2): where does the saving come from, and what did we refuse?

The bridge is the main chart; each removal step opens the list of what it
refused to count. Below, the spend waterfall (recurring only) and, in the
clean-team view, the price dispersion of one item.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components import state
from components.bridge import render_bar_detail, render_bridge, render_refused
from components.page import next_question, page_question, section, unavailable
from components.plotting import (
    bridge_figure,
    chart_with_table,
    dot_plot,
    exact_money,
    spend_colors,
)
from components.style import esc, headline
from components.trace import render_trace

from tieout import theme as t
from tieout.views import (
    Unavailable,
    bridge,
    confidence_strip,
    lever1_items,
    money,
    money_range,
    price_dispersion,
    reconciliation_text,
    synergy_waterfall,
    thousands,
    unit_price,
)

STEP_KEY = "syn_step"
_SEEN = "_syn_bridge_seen"


def _headline(frame: pd.DataFrame) -> str:
    """A finding from the bridge: what each lever gives and the largest removal."""
    lever1, lever2 = frame.iloc[-3], frame.iloc[-2]
    steps = frame[frame["kind"] == "decrease"]
    text = (
        f"Price harmonisation gives {money(lever1['amount'])} a year and volume consolidation "
        f"{money(lever2['amount'])}"
    )
    if not steps.empty and steps["amount"].min() < 0:
        largest = steps.loc[steps["amount"].idxmin()]
        text += f"; {largest['label'].lower()} removed most of the naive figure"
    return text + "."


def _waterfall(results, mode: str) -> None:
    frame = synergy_waterfall(results, mode)
    hover = [
        f"{label}<br>{exact_money(amount)}"
        for label, amount in zip(frame["label"], frame["amount"], strict=False)
    ]
    fig = bridge_figure(
        frame, colors=spend_colors(frame), hover=hover, y_title="Annual spend", height=380
    )
    table = pd.DataFrame({"Bar": frame["label"], "Amount": frame["text"]})
    net = frame.iloc[-1]
    caption = (
        f"In-scope spend of {money(frame.iloc[0]['amount'])} falls to "
        f"{money(net['amount'])} once both recurring levers are in place "
        f"(range {money_range(net['low'], net['high'])})."
    )
    index = chart_with_table(fig, table, "syn_waterfall", caption, shape="half")
    if index is not None and index < len(frame):
        bar = frame.iloc[index]
        with st.container(border=True):
            st.markdown(f"**{esc(bar['label'])}**: {esc(bar['text'])}")
            render_trace(str(bar["figure_id"]), "syn_waterfall_trace")


def _dispersion(results, mode: str) -> None:
    items = lever1_items(results, mode)
    if isinstance(items, Unavailable):
        unavailable(items)
        return
    if items.empty:
        st.info("No item has a price-harmonisation saving to compare.")
        return
    labels = dict(
        zip(items["canonical_item_id"], items["item"] + " · " + items["text"], strict=False)
    )
    item = st.selectbox(
        "Item", list(labels), format_func=labels.get, key="syn_item", label_visibility="collapsed"
    )
    data = price_dispersion(results, item, mode)
    if isinstance(data, Unavailable):
        unavailable(data)
        return
    points = data["points"].assign(
        group=lambda p: p["company"] + " · " + p["site"] + " · " + p["vendor"],
        hover=lambda p: [
            f"{v}<br>{price} per base unit<br>{q:,.0f} units on {n} lines"
            for v, price, q, n in zip(
                p["vendor"], p["price_text"], p["quantity"], p["lines"], strict=False
            )
        ],
    )
    benchmark = data["benchmark_price"]
    fig = dot_plot(
        points,
        x="price",
        y="group",
        color_by="company",
        colors={"acquirer": t.ACQUIRER, "target": t.TARGET},
        hover="hover",
        marker_line=benchmark,
        marker_line_label=f"Benchmark {unit_price(benchmark)}",
        x_title="Price per base unit",
    )
    table = points[["group", "price_text", "quantity", "lines", "change_type"]].rename(
        columns={
            "group": "Buying group",
            "price_text": "Unit price",
            "quantity": "Annual quantity",
            "lines": "Lines",
            "change_type": "Change",
        }
    )
    holder = data["benchmark_company"] or "neither company"
    cheapest = points["price_text"].iloc[points["price"].argmin()]
    dearest = points["price_text"].iloc[points["price"].argmax()]
    caption = (
        f"{len(points)} buying groups pay between {cheapest} and {dearest}; "
        f"the benchmark {unit_price(benchmark)} is held by the {holder}."
    )
    chart_with_table(fig, table, "syn_dispersion", caption)


results = state.current_results()
mode = state.view()
frame = bridge(results, mode)

page_question("Where does the saving come from, and what did we refuse to count?")
headline(_headline(frame))

section("From the naive figure to the defensible range")
bar = render_bridge("syn_bridge")
selection = None if bar is None else (bar["step"], bar["kind"])
if selection != st.session_state.get(_SEEN):  # a new selection drives the list below
    st.session_state[_SEEN] = selection
    if bar is not None and bar["kind"] == "decrease":
        st.session_state[STEP_KEY] = int(bar["step"])
if bar is not None and bar["kind"] != "decrease":
    render_bar_detail(bar, "syn_bar")

section(
    "What we refused to count",
    "Each step of the bridge removes dollars a plain best-of-both formula would have claimed.",
)
steps = frame[frame["kind"] == "decrease"]
names = {
    int(s): f"{int(s)}. {label} ({text})"
    for s, label, text in zip(steps["step"], steps["label"], steps["text"], strict=False)
}
if st.session_state.get(STEP_KEY) not in names:
    st.session_state[STEP_KEY] = min(names)
step = st.selectbox("Bridge step", list(names), format_func=names.get, key=STEP_KEY)
render_refused(step, "syn_refused")
strip = confidence_strip(results, mode)
st.caption(
    esc(
        f"Not counted but not refused: {thousands(strip['pending_review'])} of price "
        "harmonisation waits on review of uncertain matches (upside pending review)."
    )
)

left, right = st.container(key="to_grid_syn_lower").columns(2, gap="large")
with left:
    section("From baseline spend to net run-rate spend")
    _waterfall(results, mode)
    for line in reconciliation_text(results, mode)["lines"]:
        st.caption(esc(line))
with right:
    section("Price dispersion for one item")
    _dispersion(results, mode)

next_question("What could go wrong?", "risk_roadmap")
