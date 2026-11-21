"""``app/components/state.py``: the session's results, assumptions and decisions.

Each test drives a tiny script through ``AppTest`` so that ``st.session_state``
behaves as in the app; ``ops`` lists the state calls to make on the next run,
and ``out`` holds what the script read back.
"""

from __future__ import annotations

import time

import pytest
from streamlit.testing.v1 import AppTest

from tieout.match.review import DECISION_COLUMNS


def _script() -> None:
    import streamlit as st
    from components import state

    for op, args in st.session_state.pop("ops", []):
        try:
            getattr(state, op)(*args)
            st.session_state["error"] = None
        except ValueError as exc:
            st.session_state["error"] = str(exc)
    results = state.current_results()
    st.session_state["out"] = {
        "recurring_base": float(results.totals["recurring"]["base"]),
        "recurring": dict(results.totals["recurring"]),
        "same_vendor_base": float(results.assumptions["lever1"]["same_vendor"]["base"]),
        "in_force": state.assumptions()["lever1"]["same_vendor"]["base"],
        "decisions": state.decisions(),
        "is_demo": state.is_demo(),
        "view": state.view(),
        "scenarios": state.scenarios(),
        "scenario": results.meta.get("scenario"),
        "results_id": id(results),
    }


def _app() -> AppTest:
    return AppTest.from_function(_script, default_timeout=60).run()


def _do(at: AppTest, *ops: tuple[str, tuple]) -> dict:
    at.session_state["ops"] = list(ops)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at.session_state["out"]


@pytest.fixture(scope="module")
def pending_pair() -> tuple[str, str]:
    """The undecided item match with the largest stake in the demo queue."""
    from components.state import DEMO_DIR

    from tieout.results import Results

    queue = Results.load(DEMO_DIR).review_queue
    items = queue[queue["type"] == "item_match"].sort_values(
        ["stake", "pair_id"], ascending=[False, True]
    )
    return str(items["pair_id"].iloc[0]), "item_match"


def test_demo_by_default_and_rerun_is_cached() -> None:
    at = _app()
    out = at.session_state["out"]
    assert out["is_demo"] and out["view"] == "clean" and out["scenario"] == "demo"
    assert list(out["decisions"].columns) == list(DECISION_COLUMNS)
    assert out["decisions"].empty
    again = _do(at)
    assert again["results_id"] == out["results_id"]  # nothing changed, nothing recomputed


def test_assumption_change_moves_the_headline_and_reset_restores_it() -> None:
    at = _app()
    before = at.session_state["out"]
    started = time.perf_counter()
    lower = _do(at, ("set_assumptions", ({"lever1": {"same_vendor": {"base": 0.55}}},)))
    assert time.perf_counter() - started < 2.0  # PRD 6.7 asks 0.5 s on the engine; app re-run
    assert lower["same_vendor_base"] == 0.55 and lower["in_force"] == 0.55
    assert lower["recurring_base"] < before["recurring_base"]
    started = time.perf_counter()
    _do(at)
    assert time.perf_counter() - started < 1.0  # re-run after a change is cached
    reset = _do(at, ("reset_assumptions", ()))
    assert reset["recurring_base"] == pytest.approx(before["recurring_base"], abs=0.01)
    assert reset["in_force"] == before["in_force"]


def test_invalid_assumptions_raise_and_leave_the_session_unchanged() -> None:
    at = _app()
    before = at.session_state["out"]
    out = _do(at, ("set_assumptions", ({"lever1": {"same_vendor": {"base": 0.95}}},)))
    assert at.session_state["error"]  # base above high
    assert out["recurring_base"] == before["recurring_base"]
    assert out["in_force"] == before["in_force"]


def test_decision_changes_results_and_undo_restores_them(pending_pair) -> None:
    pair_id, pair_type = pending_pair
    at = _app()
    before = at.session_state["out"]
    approved = _do(at, ("record_decision", (pair_id, pair_type, "approve", None, "same part")))
    assert approved["recurring_base"] != pytest.approx(before["recurring_base"], abs=1.0)
    decisions = approved["decisions"]
    assert list(decisions["pair_id"]) == [pair_id]
    assert decisions["decision"].iloc[0] == "approve" and decisions["note"].iloc[0] == "same part"
    assert decisions["decided_at"].iloc[0].endswith("Z")
    # A second decision on the same pair replaces the first (keyed by pair id).
    deferred = _do(at, ("record_decision", (pair_id, pair_type, "defer")))
    assert list(deferred["decisions"]["decision"]) == ["defer"]
    undone = _do(at, ("undo_last_decision", ()))
    assert undone["decisions"].empty
    assert undone["recurring_base"] == pytest.approx(before["recurring_base"], abs=0.01)
    assert undone["recurring"] == pytest.approx(before["recurring"], abs=0.01)
    assert _do(at, ("undo_last_decision", ()))["decisions"].empty  # nothing left to undo


def test_decisions_and_assumptions_combine(pending_pair) -> None:
    pair_id, pair_type = pending_pair
    at = _app()
    _do(at, ("record_decision", (pair_id, pair_type, "approve")))
    both = _do(at, ("set_assumptions", ({"lever1": {"same_vendor": {"base": 0.55}}},)))
    assert both["same_vendor_base"] == 0.55 and len(both["decisions"]) == 1
    only_decision = _do(at, ("reset_assumptions", ()))
    assert only_decision["recurring_base"] > both["recurring_base"]


def test_uploaded_results_and_reset_to_demo(pending_pair) -> None:
    from dataclasses import replace

    from components.state import demo_results

    at = _app()
    demo = at.session_state["out"]
    uploaded = replace(demo_results(), meta={**demo_results().meta, "scenario": "upload"})
    out = _do(
        at,
        ("set_assumptions", ({"lever1": {"same_vendor": {"base": 0.55}}},)),
        ("set_uploaded_results", (uploaded,)),
    )
    assert not out["is_demo"] and out["scenario"] == "upload"
    assert out["in_force"] == demo["in_force"]  # overrides on other data are cleared
    out = _do(at, ("reset_to_demo", ()))
    assert out["is_demo"] and out["scenario"] == "demo"
    assert out["recurring_base"] == pytest.approx(demo["recurring_base"], abs=0.01)


def test_scenarios_are_named_copies_of_the_assumptions() -> None:
    at = _app()
    _do(at, ("set_assumptions", ({"lever1": {"same_vendor": {"base": 0.55}}},)))
    out = _do(at, ("save_scenario", ("Tighter",)), ("reset_assumptions", ()))
    assert out["scenarios"]["Tighter"]["lever1"]["same_vendor"]["base"] == 0.55
    assert out["in_force"] == 0.70
    _do(at, ("save_scenario", ("  ",)))
    assert at.session_state["error"]
