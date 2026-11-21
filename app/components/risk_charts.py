"""Plotly figures for Risk & roadmap (PRD 6.8): concentration, prioritisation matrix, phasing.

Each function draws a view function's frame as it is; nothing here computes a
saving, a share or a cost. Colours come from ``tieout.theme``.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from components.plotting import axis_money, exact_money, themed, wrap_label
from tieout import theme as t
from tieout.views import money, percent, thousands

__all__ = [
    "WAVE_COLORS",
    "WAVE_NAMES",
    "concentration_figure",
    "matrix_figure",
    "phasing_figure",
]

WAVE_NAMES = {
    1: "Wave 1: start within 100 days",
    2: "Wave 2: months 4 to 12",
    3: "Wave 3: beyond 12 months",
}
WAVE_COLORS = {1: t.TEAL, 2: t.ACQUIRER, 3: t.TARGET}
#: Vendor segments, largest first: the lead vendor in teal, then quieter greys.
_SEGMENT_COLORS = [t.TEAL, "#5F8F89", "#8FB2AD", "#B9CFCB", "#D5E2DF", t.BORDER]
_OTHER = "All other vendors"


def concentration_figure(vendors: pd.DataFrame, categories: list[str]) -> go.Figure:
    """Horizontal stacked bars, before and after consolidation, one pair per category.

    Segments are the category's vendors (largest after consolidation first);
    a marker on the "after" bar shows the cap.
    """
    frame = vendors[vendors["category"].isin(categories)].copy()
    frame["slot"] = frame.groupby("category").cumcount()
    rows = [(c, w) for c in categories for w in ("After", "Before")]
    ylabels = {(c, w): f"{wrap_label(c, 44)}<br>{w.lower()}" for c, w in rows}
    fig = go.Figure()
    for slot in range(int(frame["slot"].max()) + 1 if len(frame) else 0):
        part = frame[frame["slot"] == slot]
        for when, column in (("Before", "share_before"), ("After", "share_after")):
            labels = [ylabels[(c, when)] for c in part["category"]]
            fig.add_bar(
                y=labels,
                x=part[column],
                orientation="h",
                marker={
                    "color": _SEGMENT_COLORS[min(slot, len(_SEGMENT_COLORS) - 1)],
                    "line": {"color": t.SURFACE, "width": 1},
                },
                text=[percent(s) if s >= 0.08 else "" for s in part[column]],
                textposition="inside",
                textfont={"color": t.INK if slot else t.SURFACE, "size": t.CHART_LABEL},
                hovertext=[
                    f"{v}<br>{when.lower()} consolidation: {percent(s)} of category spend"
                    for v, s in zip(part["vendor"], part[column], strict=True)
                ],
                hoverinfo="text",
                showlegend=False,
                name=f"{when} {slot}",
            )
    caps = frame.drop_duplicates("category").set_index("category")["cap"]
    cap_rows = [(c, caps[c]) for c in categories if c in caps.index and not math.isnan(caps[c])]
    fig.add_scatter(
        x=[cap for _, cap in cap_rows],
        y=[ylabels[(c, "After")] for c, _ in cap_rows],
        mode="markers",
        marker={"symbol": "line-ns", "size": 30, "line": {"color": t.RED, "width": 3}},
        hovertext=[f"Cap: {percent(cap)} of category spend" for _, cap in cap_rows],
        hoverinfo="text",
        showlegend=False,
        name="Cap",
    )
    fig.update_layout(barmode="stack", bargap=0.25)
    fig.update_xaxes(range=[0, 1.02], tickformat=".0%", title_text="Share of category spend")
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=[ylabels[r] for r in reversed(rows)],
        automargin=True,
    )
    return themed(fig, height=max(320, 40 * len(rows) + 70))


def matrix_figure(matrix: pd.DataFrame) -> go.Figure:
    """Saving against complexity, one bubble per opportunity, coloured by wave, sized by spend.

    A single trace carries every bubble so that a selected point's index is its
    row in ``matrix``; the legend entries are empty traces. Labels: top ten only.
    """
    spend = matrix["spend"].clip(lower=0.0)
    top = float(spend.max()) if len(spend) else 0.0
    sizeref = 2.0 * top / (38.0**2) if top > 0 else 1.0
    labelled = matrix["show_label"].to_numpy()
    fig = go.Figure()
    fig.add_scatter(
        x=matrix["complexity"],
        y=matrix["base"],
        mode="markers+text",
        marker={
            "size": spend,
            "sizemode": "area",
            "sizeref": sizeref,
            "sizemin": 5,
            "color": [WAVE_COLORS.get(int(w), t.MUTED) for w in matrix["wave"]],
            "opacity": 0.7,
            "line": {"color": t.SURFACE, "width": 1},
        },
        text=[
            wrap_label(label, 26) if show else ""
            for label, show in zip(matrix["label"], labelled, strict=True)
        ],
        textposition="top center",
        textfont={"size": t.CHART_LABEL, "color": t.INK},
        hovertext=[
            f"{label}<br>Saving {exact_money(base)} a year<br>Complexity {c:.1f}"
            f"<br>Spend {money(s)}<br>{WAVE_NAMES.get(int(w), '')}"
            for label, base, c, s, w in zip(
                matrix["label"],
                matrix["base"],
                matrix["complexity"],
                matrix["spend"],
                matrix["wave"],
                strict=True,
            )
        ],
        hoverinfo="text",
        showlegend=False,
        name="Opportunities",
    )
    for wave, name in WAVE_NAMES.items():
        fig.add_scatter(
            x=[None],
            y=[None],
            mode="markers",
            marker={"size": 11, "color": WAVE_COLORS[wave]},
            name=name,
            hoverinfo="skip",
        )
    fig.update_xaxes(title_text="Complexity (1 easy, 5 hard)", range=[0.8, 5.2])
    peak = float(matrix["base"].max()) if len(matrix) else 0.0
    # Headroom so the labels of the largest bubbles are not cut off at the top edge.
    fig.update_yaxes(
        title_text="Annual saving, base case",
        **axis_money(),
        range=[0, peak * 1.3] if peak > 0 else None,
        rangemode="tozero",
    )
    return themed(fig, height=520, legend=True)


def phasing_figure(quarters: pd.DataFrame) -> go.Figure:
    """Realised savings by quarter as a stacked area by wave, one-time costs as bars below."""
    x = [f"Q{int(q)}" for q in quarters["quarter"]]
    fig = go.Figure()
    for wave, name in WAVE_NAMES.items():
        values = quarters[f"wave_{wave}"]
        fig.add_scatter(
            x=x,
            y=values,
            mode="lines",
            stackgroup="savings",
            line={"width": 0.5, "color": WAVE_COLORS[wave]},
            fillcolor=WAVE_COLORS[wave],
            name=name,
            hovertext=[
                f"{name}<br>Q{int(q)}: {exact_money(v)}"
                for q, v in zip(quarters["quarter"], values, strict=True)
            ],
            hoverinfo="text",
        )
    fig.add_bar(
        x=x,
        y=quarters["cost"],
        marker={"color": t.RED},
        name="One-time costs",
        hovertext=[
            f"One-time costs<br>Q{int(q)}: {exact_money(c)}"
            for q, c in zip(quarters["quarter"], quarters["cost"], strict=True)
        ],
        hoverinfo="text",
    )
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="Realised in the quarter", **axis_money())
    fig.update_xaxes(title_text="Quarter after close", type="category")
    return themed(fig, height=420, legend=True)


def year_table(years: pd.DataFrame) -> pd.DataFrame:
    """Phasing by year as display text: savings by wave, one-time costs and net, with the range."""
    label = [f"Year {y}" if y != "Total" else "Three years" for y in years["year"]]
    return pd.DataFrame(
        {
            "Period": label,
            "Wave 1": [thousands(v) for v in years["wave_1"]],
            "Wave 2": [thousands(v) for v in years["wave_2"]],
            "Wave 3": [thousands(v) for v in years["wave_3"]],
            "Savings": [thousands(v) for v in years["savings"]],
            "One-time costs": [thousands(v) for v in years["cost"]],
            "Net (low)": [thousands(v) for v in years["net_low"]],
            "Net (base)": [thousands(v) for v in years["net_base"]],
            "Net (high)": [thousands(v) for v in years["net_high"]],
        }
    )
