"""What was received and what state it is in (PRD 6.3 Data screen).

Reads the session's results through the view functions only; the same blocks
describe the demo and uploaded data. Nothing here is computed from raw frames.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from components.page import missing_data, section
from components.plotting import AXIS_MONEY, exact_money, show_chart, themed
from components.style import esc, figure_card
from tieout import theme as t
from tieout.results import Results
from tieout.views import money, spend_pareto, thousands

__all__ = [
    "finding_headline",
    "pareto_figure",
    "render_findings",
    "render_pareto",
    "render_received",
]

TOP_BARS = 60  # bars drawn per panel; the cumulative line is still computed over every vendor
_SEVERITY_LABEL = {"blocking": "Blocking", "warning": "Warning", "info": "Note"}


def _period_text(period: dict[str, Any]) -> str:
    if not period:
        return "Not stated (aggregated data)"
    start, end = pd.Period(period["start"], "M"), pd.Period(period["end"], "M")
    return f"{start.strftime('%b %Y')} to {end.strftime('%b %Y')} ({period['months']} months)"


def finding_headline(summary: dict[str, Any]) -> str:
    """A finding for the page headline: volume received, and what state it is in."""
    rows = sum(summary["rows"].values())
    spend = summary["in_scope_spend"]["total"]
    findings = summary["findings"]
    if findings.empty:
        state = "with nothing to fix"
    else:
        blocking = int((findings["severity"] == "blocking").sum())
        warnings = findings[findings["severity"] == "warning"]
        affected = float(warnings["amount"].sum())
        state = (
            f"with {blocking} blocking error{'s' if blocking != 1 else ''}"
            if blocking
            else f"in usable shape, with {len(warnings)} warning{'s' if len(warnings) != 1 else ''}"
            + (f" touching up to {money(affected)}" if len(warnings) else "")
        )
    return f"{rows:,} purchasing lines worth {money(spend)} a year were received, {state}."


def render_received(results: Results, summary: dict[str, Any]) -> None:
    """Files, rows, period, currency and spend: what came in."""
    section("What came in")
    names = results.lines.groupby("company")["source_file"].first().to_dict()
    currency = results.meta.get("reporting_currency", "USD")
    columns = st.columns(4)
    with columns[0]:
        total = sum(summary["rows"].values())
        figure_card(
            "Files",
            "Two purchasing files",
            f"{total:,} lines",
            f"Acquirer {summary['rows'].get('acquirer', 0):,}, "
            f"target {summary['rows'].get('target', 0):,}.",
        )
    with columns[1]:
        figure_card(
            "Period",
            "Twelve-month window",
            _period_text(summary["period"]).split(" (")[0],
            "Scaled to twelve months; see the findings."
            if summary["scaled"]
            else "A full twelve months, no scaling.",
        )
    with columns[2]:
        figure_card("Currency", "Reporting currency", str(currency), "Converted at fixed rates.")
    with columns[3]:
        figure_card(
            "Spend",
            "In-scope annual spend",
            money(summary["in_scope_spend"]["total"]),
            f"{money(summary['in_scope_spend'].get('acquirer', 0))} acquirer, "
            f"{money(summary['in_scope_spend'].get('target', 0))} target.",
        )
    table = pd.DataFrame(
        {
            "Company": [c.capitalize() for c in ("acquirer", "target")],
            "File": [names.get(c, "") for c in ("acquirer", "target")],
            "Lines in file": [summary["rows"].get(c, 0) for c in ("acquirer", "target")],
            "In-scope spend": [
                thousands(summary["in_scope_spend"].get(c, 0)) for c in ("acquirer", "target")
            ],
        }
    )
    st.dataframe(table, hide_index=True, width="stretch")
    no_item = summary["not_item_addressable"]
    st.caption(
        esc(
            f"{no_item['text']}; {money(summary['unmapped_spend'])} sits in categories "
            "not mapped to the common taxonomy. Both stay in vendor totals but cannot be "
            "price-compared."
        )
    )
    for message in summary["switched_off"].values():
        missing_data(message)


def _findings_table(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Company": frame["company"].str.capitalize(),
            "Finding": frame["message"],
            "Rows": frame["rows"],
            "Value affected": frame["amount_text"],
            "What to do": frame["fix"],
        }
    )


def render_findings(summary: dict[str, Any]) -> None:
    """The data-quality report: blocking first, warnings and notes collapsed (PRD 6.13)."""
    section("What state it is in", "Row counts and the annual dollar value each finding touches.")
    findings = summary["findings"]
    if findings.empty:
        st.success("No findings: every row passed validation.", icon=":material/check_circle:")
        return
    for severity in ("blocking", "warning", "info"):
        part = findings[findings["severity"] == severity]
        if part.empty:
            continue
        rows, amount = int(part["rows"].sum()), float(part["amount"].sum())
        label = f"{_SEVERITY_LABEL[severity]}s: {len(part)} ({rows:,} rows, {thousands(amount)})"
        if severity == "blocking":
            st.error(label, icon=":material/error:")
            st.dataframe(_findings_table(part), hide_index=True, width="stretch")
        else:
            with st.expander(label, expanded=False):
                st.dataframe(_findings_table(part), hide_index=True, width="stretch")


def pareto_figure(panel: pd.DataFrame, title: str, share: float, at: int) -> go.Figure:
    """Spend bars and the cumulative-share line (the one dual axis allowed, PRD 6.8)."""
    shown = panel.head(TOP_BARS)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(
        x=shown["rank"],
        y=shown["spend"],
        name="Spend",
        marker_color=t.MUTED,
        customdata=shown["label"],
        hovertemplate="%{customdata}<br>Rank %{x}<br>%{y:$,.0f}<extra></extra>",
    )
    fig.add_scatter(
        x=shown["rank"],
        y=shown["cumulative_share"],
        name="Cumulative share",
        mode="lines",
        line={"color": t.ACQUIRER, "width": 2},
        hovertemplate="Top %{x} vendors<br>%{y:.1%} of spend<extra></extra>",
        secondary_y=True,
    )
    fig.add_hline(y=share, line_dash="dot", line_color=t.TEAL, secondary_y=True)
    if at <= TOP_BARS:
        fig.add_vline(x=at, line_dash="dot", line_color=t.TEAL)
    fig.update_yaxes(title_text="Spend per vendor", tickformat=AXIS_MONEY, secondary_y=False)
    fig.update_yaxes(
        title_text="Cumulative share", tickformat=".0%", range=[0, 1.02], secondary_y=True
    )
    fig.update_xaxes(title_text="Vendors, largest first")
    fig.update_layout(title={"text": title, "font": {"size": 14}})
    return themed(fig, height=340)


def render_pareto(results: Results, mode: str) -> None:
    """Vendor fragmentation before and after matching (PRD 6.8 spend Pareto)."""
    data = spend_pareto(results, mode)
    to = data["vendors_to_share"]
    share = data["share"]
    section(
        f"{data['vendor_records']:,} vendor records are {data['parent_vendors']:,} companies",
        f"{share:.0%} of spend sits with "
        f"{to['after']:,} parent vendors once duplicates are merged, against {to['before']:,} "
        "vendor records before.",
    )
    as_table = st.toggle("View as table", key="data_pareto_as_table")
    panels = (
        ("Before matching: vendor records", data["before"], to["before"], "before"),
        ("After matching: parent vendors", data["after"], to["after"], "after"),
    )
    if as_table:
        for title, panel, _, key in panels:
            st.markdown(f"**{esc(title)}**")
            st.dataframe(
                panel.head(TOP_BARS)
                .rename(
                    columns={
                        "rank": "Rank",
                        "label": "Vendor",
                        "spend": "Spend",
                        "cumulative_share": "Cumulative share",
                    }
                )
                .assign(Spend=lambda f: f["Spend"].map(exact_money)),
                hide_index=True,
                width="stretch",
                key=f"data_pareto_table_{key}",
            )
    else:
        for column, (title, panel, at, key) in zip(st.columns(2), panels, strict=True):
            with column:
                show_chart(
                    pareto_figure(panel, title, share, at), f"data_pareto_{key}", selectable=False
                )
    st.caption(
        esc(
            f"Before matching it takes {to['before']:,} vendor records to reach "
            f"{share:.0%} of spend; after matching it takes {to['after']:,} parent vendors."
        ).replace("$", "\\$")
    )
