"""The accuracy scorecard against the naive baseline and the threshold curves (PRD 4.7, 6.2).

Figures come from ``scorecard_table`` and ``sensitivity_curves``; this module formats and draws.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import state
from components.page import unavailable
from components.plotting import axis_money, chart_with_table, hover_amount, themed
from tieout import theme as t
from tieout.views import Unavailable, scorecard_table, sensitivity_curves, thousands

_CURVES = {
    "vendor_auto": "Vendor automatic threshold (name score)",
    "item_auto_cosine": "Item automatic threshold (cosine)",
}


def target_text(raw: str) -> str:
    """``>= 0.98`` as ``at least 98.0%``, so targets read like the figures beside them."""
    direction, _, bound = str(raw).partition(" ")
    if not bound:
        return ""
    words = {">=": "at least", "<=": "at most"}.get(direction, direction)
    return f"{words} {float(bound):.1%}"


def _pct(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:.1%}"


def _gate(passed: object) -> str:
    if passed is None or (isinstance(passed, float) and math.isnan(passed)):
        return "No gate"
    return "Passed" if passed else "Missed"


def _scorecard(table: pd.DataFrame) -> None:
    fig = go.Figure()
    for column, name, color in (
        ("tool", "Tie-Out", t.ACQUIRER),
        ("baseline", "Naive baseline", t.CONTROL),
    ):
        fig.add_bar(
            x=table["label"],
            y=table[column],
            name=name,
            marker={"color": color},
            hovertemplate="%{x}<br>" + name + ": %{y:.1%}<extra></extra>",
        )
    fig.update_layout(barmode="group")
    fig.update_yaxes(tickformat=".0%", title_text="Held-out seed")
    fig = themed(fig, height=340, legend=True)
    shown = pd.DataFrame(
        {
            "Metric": table["label"],
            "Tie-Out": [_pct(v) for v in table["tool"]],
            "Naive baseline": [_pct(v) for v in table["baseline"]],
            "Target": [target_text(v) for v in table["target"]],
            "Gate": [_gate(p) for p in table["passed"]],
        }
    )
    gap = (table["baseline"] - table["tool"]).abs()
    worst = table.loc[gap.idxmax()]
    caption = (
        f"Measured against hidden truth on the held-out seed: {worst['label'].lower()} is "
        f"{_pct(worst['tool'])} for Tie-Out and {_pct(worst['baseline'])} for the naive baseline."
    )
    chart_with_table(fig, shown, "mt_scorecard", caption, shape="wide")


def _curve(name: str, frame: pd.DataFrame, current: dict) -> None:
    fig = go.Figure()
    fig.add_scatter(
        x=frame["threshold"],
        y=frame["recurring_high"],
        mode="lines",
        line={"width": 0},
        hoverinfo="skip",
        showlegend=False,
    )
    fig.add_scatter(
        x=frame["threshold"],
        y=frame["recurring_low"],
        mode="lines",
        line={"width": 0},
        fill="tonexty",
        fillcolor=t.TEAL_TINT,
        hoverinfo="skip",
        name="Low to high",
    )
    fig.add_scatter(
        x=frame["threshold"],
        y=frame["recurring_base"],
        mode="lines+markers",
        line={"color": t.TEAL, "width": 2},
        name="Base case",
        hovertemplate=f"Threshold %{{x}}<br>Base {hover_amount()}<extra></extra>",
    )
    fig.add_vline(x=current[name], line={"color": t.INK, "width": 1, "dash": "dash"})
    fig.update_xaxes(title_text=_CURVES[name])
    fig.update_yaxes(title_text="Recurring saving", **axis_money())
    fig = themed(fig, height=300, legend=True)
    table = pd.DataFrame(
        {
            "Threshold": frame["threshold"],
            "Low": [thousands(v) for v in frame["recurring_low"]],
            "Base": [thousands(v) for v in frame["recurring_base"]],
            "High": [thousands(v) for v in frame["recurring_high"]],
        }
    )
    base = frame["recurring_base"]
    caption = (
        f"The base saving stays between {thousands(base.min())} and {thousands(base.max())} "
        f"across this range; the dashed line is the threshold in use ({current[name]:g})."
    )
    chart_with_table(fig, table, f"mt_curve_{name}", caption, shape="half")


def render_scorecard() -> None:
    table = scorecard_table(state.current_results(), state.view())
    if isinstance(table, Unavailable):
        unavailable(table)
    else:
        _scorecard(table)


def render_sensitivity() -> None:
    curves = sensitivity_curves(state.current_results(), state.view())
    if isinstance(curves, Unavailable):
        unavailable(curves)
        return
    left, right = st.container(key="to_grid_mt_curves").columns(2, gap="large")
    for column, name in zip((left, right), _CURVES, strict=True):
        with column:
            _curve(name, curves[name], curves["current"])
