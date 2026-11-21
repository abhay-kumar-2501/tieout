"""Risk & roadmap (PRD 5.5-5.7, 6.3, 6.8): what do we give up for resilience, and what happens when?

The concentration view with the live cap slider (outside any form, PRD 9.3),
the prioritisation matrix with drill-down to an opportunity and its working,
and phasing by quarter and by year with one-time costs and the three-year net.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components import state
from components.page import (
    empty_state,
    error_state,
    missing_data,
    next_question,
    page_question,
    section,
)
from components.plotting import chart_with_table
from components.risk_charts import (
    WAVE_NAMES,
    concentration_figure,
    matrix_figure,
    phasing_figure,
    year_table,
)
from components.style import esc, figure_card, headline
from components.trace import show_working

from tieout.views import (
    concentration,
    money,
    money_range,
    percent,
    phasing_by_quarter,
    phasing_by_year,
    prioritisation_matrix,
    thousands,
)

CAP_KEY = "risk_cap_pct"
_CAP_ERROR = "_risk_cap_error"
CATEGORIES_SHOWN = 8


def _on_cap_change() -> None:
    """Slider released: set the standard-category cap through the one state function."""
    try:
        state.set_assumptions({"caps": {"standard": st.session_state[CAP_KEY] / 100}})
        st.session_state[_CAP_ERROR] = None
    except ValueError as exc:
        st.session_state[_CAP_ERROR] = str(exc)


def _cap_control() -> None:
    caps = state.assumptions()["caps"]
    current = round(float(caps["standard"]) * 100)
    st.slider(
        "Concentration cap for standard categories",
        min_value=0,
        max_value=100,
        value=current,
        step=1,
        format="%d%%",
        key=CAP_KEY,
        on_change=_on_cap_change,
        help="The largest share any one parent vendor may hold of a standard category after "
        "consolidation. Lower it to protect supply; the saving given up rises.",
    )
    st.caption(
        esc(
            f"Critical categories stay at {percent(caps['critical'])} and non-critical at "
            f"{percent(caps['non_critical'])}; change them on the Assumptions screen."
        )
    )
    if st.session_state.get(_CAP_ERROR):
        st.error(esc(st.session_state[_CAP_ERROR]), icon=":material/error:")


def _concentration(results, mode: str) -> None:
    data = concentration(results, mode)
    cats, vendors = data["categories"], data["vendors"]
    if vendors.empty:
        empty_state(
            "No concentration data",
            "This run has no category-level vendor spend to measure concentration on.",
        )
        return
    forgone = float(results.totals["lever2"]["savings_forgone"])
    left, right = st.columns([1, 2], vertical_alignment="top")
    with left:
        _cap_control()
        figure_card(
            "Recurring, every year",
            "Savings forgone to protect supply resilience",
            thousands(forgone),
            "Volume-consolidation saving given up because no vendor may exceed its cap.",
        )
        show_working("lever2.savings_forgone", "the savings forgone", key="risk_forgone")
    with right:
        shown = cats.head(CATEGORIES_SHOWN)["category"].tolist()
        fig = concentration_figure(vendors, shown)
        table = pd.DataFrame(
            {
                "Category": cats["category"],
                "Cap": [percent(c) if c == c else "mixed" for c in cats["cap"]],
                "Concentration before": cats["hhi_before"].round(0).astype(int),
                "Concentration after": cats["hhi_after"].round(0).astype(int),
                "Savings forgone": [thousands(v) for v in cats["savings_forgone"]],
            }
        )
        limited = int(cats["cap_limits"].sum())
        caption = (
            f"The cap limits consolidation in {limited} of {len(cats)} categories; the "
            f"{min(CATEGORIES_SHOWN, len(cats))} where it costs most are shown. Red marks are "
            "the caps; the concentration index runs from 0 to 10,000."
        )
        chart_with_table(fig, table, "risk_concentration", caption)


def _matrix_detail(matrix: pd.DataFrame, index: int, mode: str) -> None:
    row = matrix.iloc[index]
    lever = {1: "Price harmonisation", 2: "Volume consolidation", 3: "Payment terms"}.get(
        int(row["lever"]), ""
    )
    with st.container(border=True):
        st.markdown(f"**{esc(row['label'])}**")
        st.caption(
            esc(
                f"{lever} · saving {thousands(row['base'])} a year · complexity "
                f"{row['complexity']:.1f} of 5 · spend {thousands(row['spend'])} · "
                f"{WAVE_NAMES.get(int(row['wave']), '')}"
            )
        )
        figure_id = row["figure_id"]
        if isinstance(figure_id, str) and figure_id:
            show_working(figure_id, str(row["label"]), key=f"risk_matrix_{index}")
        else:
            st.caption("Opportunity detail is not available in the integration-office view.")


def _matrix(results, mode: str) -> None:
    matrix = prioritisation_matrix(results, mode)
    if matrix.empty:
        empty_state("No opportunities", "No opportunity has a positive base-case saving to rank.")
        return
    table = pd.DataFrame(
        {
            "Opportunity": matrix["label"],
            "Saving": [thousands(v) for v in matrix["base"]],
            "Complexity": matrix["complexity"].round(1),
            "Spend": [thousands(v) for v in matrix["spend"]],
            "Wave": [WAVE_NAMES.get(int(w), "") for w in matrix["wave"]],
        }
    )
    wave1 = matrix[matrix["wave"] == 1]
    caption = (
        f"{len(matrix):,} opportunities; {len(wave1):,} can start within 100 days of close "
        f"and carry {money(wave1['base'].sum())} a year. Bubble size is the spend behind each; "
        "the ten largest savings are labelled."
    )
    index = chart_with_table(matrix_figure(matrix), table, "risk_matrix", caption)
    if index is not None and index < len(matrix):
        _matrix_detail(matrix, index, mode)
    else:
        st.caption("Select a bubble or a table row to open that opportunity.")


def _phasing(results, mode: str) -> None:
    totals = results.totals["phasing"]
    if totals.get("method") != "contract":
        missing_data(
            "Add contract end dates to enable contract-aware phasing; the global ramp "
            "(40%, 85%, 100% of run-rate) is used until then."
        )
    quarters = phasing_by_quarter(results, mode)
    years = phasing_by_year(results, mode)
    net = years.iloc[-1]
    c1, c2 = st.columns([2, 1])
    with c2:
        figure_card(
            "Three-year value",
            "Net three-year value",
            money_range(net["net_low"], net["net_high"]),
            f"Base {money(net['net_base'])}: savings realised in years 1 to 3 less "
            f"{money(-net['cost'])} of one-time costs.",
        )
        show_working("phasing.net_three_year.base", "the net three-year value", key="risk_net")
    with c1:
        shown = pd.DataFrame(
            {
                "Quarter": [f"Q{int(q)}" for q in quarters["quarter"]],
                "Savings": [thousands(v) for v in quarters["savings"]],
                "One-time costs": [thousands(v) for v in quarters["cost"]],
                "Payment-terms cash (one-time)": [thousands(v) for v in quarters["cash"]],
            }
        )
        caption = (
            f"Realised savings reach {thousands(quarters['savings'].iloc[-1])} a quarter by "
            f"quarter 12; one-time costs of {thousands(-quarters['cost'].sum())} fall "
            "mostly in the early quarters."
        )
        chart_with_table(phasing_figure(quarters), shown, "risk_phasing", caption)
    st.markdown("**By year**")
    st.dataframe(year_table(years), hide_index=True, width="stretch", key="risk_years")
    beyond = totals.get("beyond_month_36") or []
    if beyond:
        st.caption(
            f"{len(beyond):,} opportunities start after month 36: they count towards the "
            "run-rate but add nothing to the three-year figure."
        )
    cash = float(quarters["cash"].sum())
    st.caption(
        esc(
            f"Payment-terms cash of {thousands(cash)} is released once and shown on its own; "
            "it is not part of the savings or the net value."
        )
    )


def _guard(name: str, draw, *args) -> None:
    """One section failing must not take the page down (PRD 6.13)."""
    try:
        draw(*args)
    except Exception as exc:  # noqa: BLE001
        error_state(
            f"The {name} could not be drawn.", f"({type(exc).__name__}: {exc})", "Reload the page."
        )


results = state.current_results()
mode = state.view()
page_question("What do we give up for resilience, and what happens when?")

forgone = float(results.totals["lever2"]["savings_forgone"])
net_total = phasing_by_year(results, mode).iloc[-1]
headline(
    f"Protecting supply gives up {money(forgone)} of annual saving; "
    f"the first three years net {money(net_total['net_base'])} after one-time costs."
)

section(
    "How much consolidation does the cap allow?",
    "Concentration by category, before and after consolidation, against the cap.",
)
_guard("concentration view", _concentration, results, mode)

section(
    "Which opportunities come first?",
    "Saving against complexity; the waves follow from contract dates and effort.",
)
_guard("prioritisation matrix", _matrix, results, mode)

section("When do the savings arrive, and what do they cost?")
_guard("phasing view", _phasing, results, mode)

next_question("What are we assuming?", "assumptions")
