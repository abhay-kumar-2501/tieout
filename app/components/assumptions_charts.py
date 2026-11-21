"""The tornado chart and scenario table of the Assumptions screen (PRD 6.7, 6.8).

Both draw the frames of ``tornado_chart`` and ``scenario_table`` as they are.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from components.assumptions_spec import field_by_dotted, format_value
from components.plotting import axis_money, exact_money, themed, wrap_label
from tieout import theme as t
from tieout.views import money, money_range, thousands

__all__ = ["scenario_display", "tornado_figure", "tornado_table"]


def _setting(path: str, value: float) -> str:
    return format_value(field_by_dotted(path), float(value))


def tornado_figure(frame: pd.DataFrame) -> go.Figure:
    """Horizontal bars: the change in the base recurring saving at each input's low and high."""
    labels = [wrap_label(label, 30) for label in frame["label"]]
    fig = go.Figure()
    for column, setting, name, color in (
        ("effect_low", "low_setting", "At the low setting", t.CONTROL),
        ("effect_high", "high_setting", "At the high setting", t.TEAL),
    ):
        fig.add_bar(
            y=labels,
            x=frame[column],
            orientation="h",
            name=name,
            marker={"color": color},
            text=[money(v) if abs(v) >= 5e4 else "" for v in frame[column]],
            textposition="outside",
            textfont={"size": t.CHART_LABEL, "color": t.INK},
            cliponaxis=False,
            hovertext=[
                f"{label}<br>At {_setting(path, s)}: {exact_money(v)} against the base"
                for label, path, s, v in zip(
                    frame["label"], frame["assumption"], frame[setting], frame[column], strict=True
                )
            ],
            hoverinfo="text",
        )
    fig.update_layout(barmode="relative", bargap=0.3)
    fig.update_xaxes(title_text="Change in base recurring saving", **axis_money())
    fig.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=list(reversed(labels)),
        automargin=True,
    )
    return themed(fig, height=max(360, 36 * len(frame) + 100), legend=True)


def tornado_table(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Assumption": frame["label"],
            "Low setting": [
                _setting(p, v)
                for p, v in zip(frame["assumption"], frame["low_setting"], strict=True)
            ],
            "Base setting": [
                _setting(p, v)
                for p, v in zip(frame["assumption"], frame["base_setting"], strict=True)
            ],
            "High setting": [
                _setting(p, v)
                for p, v in zip(frame["assumption"], frame["high_setting"], strict=True)
            ],
            "Saving at low": [thousands(v) for v in frame["recurring_at_low"]],
            "Saving at high": [thousands(v) for v in frame["recurring_at_high"]],
            "Swing": [thousands(v) for v in frame["swing"]],
        }
    )


def scenario_display(frame: pd.DataFrame) -> pd.DataFrame:
    """The scenario totals as text; recurring and one-time figures in separate columns."""
    return pd.DataFrame(
        {
            "Scenario": frame["scenario"],
            "Recurring saving (range)": [
                money_range(lo, hi)
                for lo, hi in zip(frame["recurring_low"], frame["recurring_high"], strict=True)
            ],
            "Recurring saving (base)": [thousands(v) for v in frame["recurring_base"]],
            "Price harmonisation": [thousands(v) for v in frame["lever1_base"]],
            "Volume consolidation": [thousands(v) for v in frame["lever2_base"]],
            "One-time cash release": [thousands(v) for v in frame["cash_base"]],
            "One-time costs": [thousands(v) for v in frame["one_time_cost_base"]],
            "Net three-year value": [thousands(v) for v in frame["net_three_year_base"]],
        }
    )
