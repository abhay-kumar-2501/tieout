"""Shared Plotly helpers: the PRD 6.11 look, bridge/waterfall bars and selection events.

Charts draw view-function output as it is; nothing here computes a figure.
Bridge and waterfall charts are stacked bar traces over a transparent base
series, not the waterfall trace type, so that bar selection works (PRD 9.3).
"""

from __future__ import annotations

import math
import textwrap
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tieout import theme as t

__all__ = [
    "AXIS_MONEY",
    "bridge_colors",
    "bridge_figure",
    "chart_with_table",
    "dot_plot",
    "exact_money",
    "selected_point",
    "selected_row",
    "show_chart",
    "spend_colors",
    "themed",
    "wrap_label",
]

TRANSPARENT = "rgba(0,0,0,0)"
#: d3 tick format for money axes: $32M, $520M.
AXIS_MONEY = "$.3~s"
_CONFIG = {"displayModeBar": False, "displaylogo": False, "responsive": True}


def themed(fig: go.Figure, *, height: int = 420, legend: bool = False) -> go.Figure:
    """Apply the PRD 6.11 look: paper background, ink text, IBM Plex, quiet axes, no animation."""
    axis = {
        "gridcolor": t.BORDER,
        "linecolor": t.BORDER,
        "zerolinecolor": t.BORDER,
        "tickfont": {"color": t.MUTED, "size": 12},
        "title": {"font": {"color": t.MUTED, "size": 13}},
        "automargin": True,
    }
    fig.update_layout(
        height=height,
        paper_bgcolor=TRANSPARENT,
        plot_bgcolor=TRANSPARENT,
        font={"family": f"{t.FONT_SANS}, sans-serif", "color": t.INK, "size": 13},
        colorway=[t.ACQUIRER, t.TARGET, t.TEAL, t.MUTED, t.CONTROL],
        margin={"l": 8, "r": 8, "t": 24, "b": 8},
        hoverlabel={
            "bgcolor": t.SURFACE,
            "bordercolor": t.BORDER,
            "font": {"family": f"{t.FONT_SANS}, sans-serif", "color": t.INK, "size": 13},
        },
        showlegend=legend,
        legend={"orientation": "h", "y": 1.08, "x": 0, "font": {"color": t.MUTED, "size": 12}},
        clickmode="event+select",
        transition={"duration": 0},
    )
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def exact_money(value: float) -> str:
    """An exact dollar figure for hover text, with a minus sign: ``−$7,642,579`` (PRD 6.11)."""
    sign = "\u2212" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def wrap_label(text: str, width: int = 12) -> str:
    """A category axis label broken over lines with ``<br>`` so long step names fit."""
    lines = textwrap.wrap(str(text), width=width, break_long_words=False, break_on_hyphens=False)
    return "<br>".join(lines) or str(text)


def bridge_colors(frame: pd.DataFrame) -> list[str]:
    """Bridge bars: the naive figure muted, removals grey, defensible figures teal (savings)."""
    colors = []
    for i, kind in enumerate(frame["kind"]):
        if kind == "total":
            colors.append(t.MUTED if i == 0 else t.TEAL)
        elif kind == "decrease":
            colors.append(t.CONTROL)
        else:
            colors.append(t.TEAL)
    return colors


def spend_colors(frame: pd.DataFrame) -> list[str]:
    """Spend waterfall bars: spend totals in ink, the savings that reduce it in teal."""
    return [t.INK if kind == "total" else t.TEAL for kind in frame["kind"]]


def _range_errors(frame: pd.DataFrame) -> dict[str, Any] | None:
    """Error bars marking each bar's low-high range, where the view supplies one."""
    if "low" not in frame or frame["low"].isna().all():
        return None
    plus, minus = [], []
    for amount, low, high in zip(frame["amount"], frame["low"], frame["high"], strict=True):
        has = not (math.isnan(low) or math.isnan(high))
        plus.append(max(high, low) - amount if has else 0.0)
        minus.append(amount - min(high, low) if has else 0.0)
    return {
        "type": "data",
        "array": plus,
        "arrayminus": minus,
        "color": t.INK,
        "thickness": 1.5,
        "width": 10,
    }


def bridge_figure(
    frame: pd.DataFrame,
    *,
    colors: Sequence[str] | None = None,
    hover: Sequence[str] | None = None,
    y_title: str = "Annual saving",
    height: int = 440,
) -> go.Figure:
    """A bridge or waterfall from a view frame with ``label``, ``kind``, ``amount``,
    ``bar_base``, ``bar_height``, ``text`` (and optionally ``low`` / ``high``).

    Two stacked bar traces: the transparent base (not hoverable) and the
    visible bar, labelled directly with its figure. Selecting either selects
    the bar's index (``selected_point``).
    """
    labels = [wrap_label(label) for label in frame["label"]]
    if hover is None:
        hover = [
            f"{label}<br>{exact_money(amount)}"
            for label, amount in zip(frame["label"], frame["amount"], strict=True)
        ]
    fig = go.Figure()
    fig.add_bar(
        x=labels,
        y=frame["bar_base"],
        marker={"color": TRANSPARENT},
        hoverinfo="skip",
        showlegend=False,
        name="base",
    )
    fig.add_bar(
        x=labels,
        y=frame["bar_height"],
        marker={"color": list(colors or bridge_colors(frame)), "line": {"width": 0}},
        text=list(frame["text"]),
        textposition="outside",
        textfont={"color": t.INK, "size": 12},
        cliponaxis=False,
        hovertext=list(hover),
        hoverinfo="text",
        error_y=_range_errors(frame),
        showlegend=False,
        name="amount",
    )
    fig.update_layout(barmode="stack", bargap=0.35)
    fig.update_yaxes(title_text=y_title, tickformat=AXIS_MONEY, rangemode="tozero")
    fig.update_xaxes(tickangle=0)
    return themed(fig, height=height)


def dot_plot(
    points: pd.DataFrame,
    *,
    x: str,
    y: str,
    color_by: str,
    colors: Mapping[str, str],
    hover: str,
    marker_line: float | None = None,
    marker_line_label: str = "",
    x_title: str = "",
    height: int | None = None,
) -> go.Figure:
    """A dot plot: one marker per row, one trace per ``color_by`` value, with a reference line."""
    fig = go.Figure()
    for value, group in points.groupby(color_by, sort=True):
        fig.add_scatter(
            x=group[x],
            y=[wrap_label(v, 34) for v in group[y]],
            mode="markers",
            name=str(value).capitalize(),
            marker={"color": colors.get(str(value), t.MUTED), "size": 11, "line": {"width": 0}},
            hovertext=group[hover],
            hoverinfo="text",
        )
    if marker_line is not None and not math.isnan(marker_line):
        fig.add_vline(x=marker_line, line={"color": t.TEAL, "width": 2, "dash": "dash"})
        fig.add_annotation(  # above the plot area, so it never sits on a dot
            x=marker_line,
            y=1,
            yref="paper",
            yanchor="bottom",
            xanchor="center",
            text=marker_line_label,
            showarrow=False,
            font={"color": t.INK, "size": 12},
        )
    fig.update_xaxes(title_text=x_title)
    fig.update_yaxes(type="category", automargin=True)
    rows = points[y].nunique()
    fig = themed(fig, height=height or max(300, 120 + 40 * rows), legend=True)
    fig.update_layout(legend={"y": -0.25, "yanchor": "top"}, margin={"t": 32, "b": 16})
    return fig


def show_chart(fig: go.Figure, key: str, *, selectable: bool = True) -> Any:
    """Render ``fig`` at full width in the PRD 6.11 look; selectable charts re-run on selection."""
    if selectable:
        return st.plotly_chart(
            fig,
            key=key,
            on_select="rerun",
            selection_mode="points",
            theme=None,
            config=_CONFIG,
            width="stretch",
        )
    return st.plotly_chart(fig, key=key, theme=None, config=_CONFIG, width="stretch")


def selected_point(event: Any) -> int | None:
    """The index of the first selected point of a ``st.plotly_chart`` selection event, if any."""
    if not event:
        return None
    try:
        points = event["selection"]["points"]
    except (KeyError, TypeError):
        return None
    for point in points or []:
        for field in ("point_index", "point_number"):
            index = point.get(field) if isinstance(point, Mapping) else None
            if index is not None:
                return int(index)
    return None


def selected_row(event: Any) -> int | None:
    """The first selected row of a ``st.dataframe`` selection event, if any."""
    try:
        rows = event["selection"]["rows"]
    except (KeyError, TypeError):
        return None
    return int(rows[0]) if rows else None


def chart_with_table(fig: go.Figure, table: pd.DataFrame, key: str, caption: str) -> int | None:
    """A selectable chart with its "View as table" toggle and one-sentence caption (PRD 6.8).

    Returns the index of the selected bar or row (the same index either way).
    """
    as_table = st.toggle("View as table", key=f"{key}_as_table")
    if as_table:
        event = st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key=f"{key}_table",
        )
        index = selected_row(event)
    else:
        index = selected_point(show_chart(fig, key))
    st.caption(caption.replace("$", "\\$"))
    return index
