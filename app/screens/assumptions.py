"""Assumptions (PRD 6.7): which inputs drive the answer?

Every adjustable input as a grouped form with its default, unit and valid
range; a reset; the tornado chart of what moves the base recurring saving; and
named scenarios compared in one table. The tornado and the scenario totals run
the arithmetic many times, so they are kept in session state until the
assumptions, the saved scenarios or the view change.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import streamlit as st
from components import state
from components.assumptions_charts import scenario_display, tornado_figure, tornado_table
from components.assumptions_forms import render_forms, reset_all, summary_line
from components.page import empty_state, error_state, next_question, page_question, section
from components.plotting import chart_with_table
from components.style import esc, headline

from tieout.views import headline as headline_view
from tieout.views import money, scenario_table, tornado_chart

_SAVE_ERROR = "_asm_scenario_error"
_NAME_KEY = "asm_scenario_name"


def _cached(name: str, results, extra: str, compute: Callable[[], Any]) -> Any:
    """Keep a slow view result until the results in force (or ``extra``) change."""
    key = f"_asm_cache_{name}"
    held = st.session_state.get(key)
    if held is not None and held[0] is results and held[1] == extra:
        return held[2]
    value = compute()
    st.session_state[key] = (results, extra, value)
    return value


def _save_scenario() -> None:
    try:
        state.save_scenario(st.session_state.get(_NAME_KEY, ""))
        st.session_state[_SAVE_ERROR] = None
    except ValueError as exc:
        st.session_state[_SAVE_ERROR] = str(exc)


def _use_scenario() -> None:
    name = st.session_state.get("asm_scenario_pick")
    saved = state.scenarios()
    if name in saved:
        try:
            state.set_assumptions(saved[name])
            st.session_state[_SAVE_ERROR] = None
        except ValueError as exc:
            st.session_state[_SAVE_ERROR] = str(exc)


def _tornado(results, mode: str) -> None:
    frame = _cached("tornado", results, mode, lambda: tornado_chart(results, mode))
    if frame.empty:
        empty_state("Nothing to rank", "No assumption moves the recurring saving.")
        return
    top = frame.iloc[0]
    caption = (
        f"{top['label']} moves the base recurring saving most: {money(top['effect_low'])} at its "
        f"low setting and {money(top['effect_high'])} at its high, against the base. Other "
        "inputs are held at their current values."
    )
    chart_with_table(tornado_figure(frame), tornado_table(frame), "asm_tornado", caption)


def _scenarios(results, mode: str) -> None:
    saved = state.scenarios()
    extra = mode + json.dumps(saved, sort_keys=True, default=str)
    frame = _cached("scenarios", results, extra, lambda: scenario_table(results, saved, mode))
    st.dataframe(scenario_display(frame), hide_index=True, width="stretch", key="asm_scenarios")
    st.caption(
        esc(
            "Recurring saving is a yearly P&L figure; cash release and one-time costs are "
            "one-time amounts and are never added to it. Conservative and Stretch set every "
            "base probability to its low or high value."
        )
    )
    with st.form("asm_scenario_form", border=False):
        st.text_input(
            "Save the assumptions in force as a scenario",
            key=_NAME_KEY,
            placeholder="For example: Board case",
            help="Saved for this session only. Saving under an existing name replaces it.",
        )
        st.form_submit_button("Save scenario", on_click=_save_scenario, key="asm_scenario_save")
    if st.session_state.get(_SAVE_ERROR):
        st.error(esc(st.session_state[_SAVE_ERROR]), icon=":material/error:")
    if saved:
        pick, use = st.columns([3, 1], vertical_alignment="bottom")
        pick.selectbox("Saved scenarios", list(saved), key="asm_scenario_pick")
        use.button("Use this scenario", key="asm_scenario_use", on_click=_use_scenario)


def _guard(name: str, draw: Callable[..., None], *args) -> None:
    """One section failing must not take the page down (PRD 6.13)."""
    try:
        draw(*args)
    except Exception as exc:  # noqa: BLE001
        error_state(
            f"The {name} could not be drawn.", f"({type(exc).__name__}: {exc})", "Reload the page."
        )


results = state.current_results()
mode = state.view()
page_question("Which inputs drive the answer?")

try:
    ranked = _cached("tornado", results, mode, lambda: tornado_chart(results, mode))
    top = ranked.iloc[0]
    headline(
        f"{top['label']} moves the run-rate saving most, by up to {money(top['swing'])} "
        "across its range."
    )
except Exception:  # noqa: BLE001
    headline(headline_view(results, mode)["text"])

row = st.container(horizontal=True, vertical_alignment="center", gap="medium")
row.markdown(f"**{esc(summary_line())}**", width="content")
row.button(
    "Reset all to defaults",
    key="asm_reset_all",
    icon=":material/restart_alt:",
    on_click=reset_all,
)

section(
    "The inputs",
    "Each group is applied together with Apply changes; nothing recalculates until then.",
)
render_forms()

section("Which inputs move the answer most?")
_guard("tornado chart", _tornado, results, mode)

section("Scenarios")
_guard("scenario comparison", _scenarios, results, mode)

next_question("Take it with you", "export")
