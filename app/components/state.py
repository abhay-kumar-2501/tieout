"""The one place that holds session state (PRD 6.1 principle 7, 9.3).

Every page reads results, the view mode, assumptions and review decisions
through these functions and never touches ``st.session_state`` keys directly.

- The committed demo results are loaded once per server (``st.cache_resource``,
  shared across visitors because they are public). Uploaded results live in
  ``st.session_state`` only and are never cached across sessions or written to
  disk (PRD 9.3).
- ``current_results()`` applies this session's review decisions
  (``apply_decisions``: re-assembly from cached pair scores) and assumption
  overrides (``recompute``: arithmetic only) to the base results. Each stage is
  cached in session state against a version counter, so a re-run with nothing
  changed does no work and an assumption change re-runs only the arithmetic.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from tieout.assumptions import merge_overrides
from tieout.match.review import DECISION_COLUMNS, validate_decisions
from tieout.pipeline import apply_decisions, recompute
from tieout.results import Results

__all__ = [
    "DEMO_DIR",
    "VIEW_KEY",
    "VIEW_MODES",
    "assumptions",
    "current_results",
    "decisions",
    "demo_results",
    "is_demo",
    "record_decision",
    "reset_assumptions",
    "reset_to_demo",
    "save_scenario",
    "scenarios",
    "set_assumptions",
    "set_uploaded_results",
    "undo_last_decision",
    "view",
]

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo" / "results"

#: Header control labels -> view mode passed to every view function (PRD 6.9).
VIEW_MODES = {"Clean team": "clean", "Integration office": "masked"}
VIEW_KEY = "view_mode"

_UPLOADED = "_to_uploaded"  # Results from uploaded files, or absent for the demo
_ASSUMPTIONS = "_to_assumptions"  # full assumptions in force, or absent for the base run's
_DECISIONS = "_to_decisions"  # this session's decisions, PRD 4.5 format
_SCENARIOS = "_to_scenarios"  # name -> assumptions
_VERSION = "_to_version"  # change counters: base, decisions, assumptions
_MATCHED = "_to_matched"  # (base, decisions) versions -> Results with decisions applied
_CURRENT = "_to_current"  # (base, decisions, assumptions) versions -> Results in force


@st.cache_resource(show_spinner=False)
def _load_demo(directory: str) -> Results:
    results = Results.load(directory)
    # Build the synergy cache once, so the first assumption change re-runs only arithmetic.
    return replace(results, synergy_cache=results.cached_synergy())


def demo_results() -> Results:
    """The committed demo results (``data/demo/results``), loaded once per server."""
    return _load_demo(str(DEMO_DIR))


# ---------------------------------------------------------------- versions


def _versions() -> dict[str, int]:
    if _VERSION not in st.session_state:
        st.session_state[_VERSION] = {"base": 0, "decisions": 0, "assumptions": 0}
    return st.session_state[_VERSION]


def _bump(*parts: str) -> None:
    versions = dict(_versions())
    for part in parts:
        versions[part] += 1
    st.session_state[_VERSION] = versions


def _base() -> Results:
    uploaded = st.session_state.get(_UPLOADED)
    return uploaded if uploaded is not None else demo_results()


# ---------------------------------------------------------------- results


def _full_log(base: Results) -> pd.DataFrame:
    """The base run's own log followed by this session's decisions, last word per pair."""
    log = pd.concat([validate_decisions(base.review_log), decisions()], ignore_index=True)
    log = log.drop_duplicates("pair_id", keep="last").reset_index(drop=True)
    return validate_decisions(log)


def _matched(base: Results) -> Results:
    versions = _versions()
    token = (versions["base"], versions["decisions"])
    cached = st.session_state.get(_MATCHED)
    if cached is not None and cached[0] == token:
        return cached[1]
    matched = base if decisions().empty else apply_decisions(base, _full_log(base))
    st.session_state[_MATCHED] = (token, matched)
    return matched


def current_results() -> Results:
    """This session's results: the demo or the uploaded run, with decisions and assumptions applied.

    Cheap on a re-run: the applied results are cached in session state and
    recomputed only when the base, the decisions or the assumptions changed.
    """
    versions = _versions()
    token = (versions["base"], versions["decisions"], versions["assumptions"])
    cached = st.session_state.get(_CURRENT)
    if cached is not None and cached[0] == token:
        return cached[1]
    matched = _matched(_base())
    overrides = st.session_state.get(_ASSUMPTIONS)
    current = matched if overrides is None else recompute(matched, overrides)
    st.session_state[_CURRENT] = (token, current)
    return current


# ---------------------------------------------------------------- view mode


def view() -> str:
    """``"clean"`` or ``"masked"``, from the header's view-mode control (clean by default)."""
    return VIEW_MODES.get(st.session_state.get(VIEW_KEY), "clean")


# ---------------------------------------------------------------- assumptions


def assumptions() -> dict[str, Any]:
    """The assumptions currently in force (a copy; edit it and pass it to ``set_assumptions``)."""
    overrides = st.session_state.get(_ASSUMPTIONS)
    source = overrides if overrides is not None else _base().assumptions
    return copy.deepcopy(dict(source))


def set_assumptions(overrides: Mapping[str, Any]) -> None:
    """Merge ``overrides`` (complete or partial, nested) over the assumptions in force.

    Runs ``recompute``; invalid values raise ``ValueError`` and leave the
    session as it was.
    """
    previous = st.session_state.get(_ASSUMPTIONS)
    st.session_state[_ASSUMPTIONS] = merge_overrides(overrides, assumptions())
    _bump("assumptions")
    try:
        current_results()
    except ValueError:
        if previous is None:
            del st.session_state[_ASSUMPTIONS]
        else:
            st.session_state[_ASSUMPTIONS] = previous
        _bump("assumptions")
        raise


def reset_assumptions() -> None:
    """Return to the base run's assumptions (the defaults for the demo)."""
    if _ASSUMPTIONS in st.session_state:
        del st.session_state[_ASSUMPTIONS]
        _bump("assumptions")


# ---------------------------------------------------------------- scenarios


def scenarios() -> dict[str, dict[str, Any]]:
    """Scenarios saved this session: name -> a complete copy of the assumptions (PRD 6.7)."""
    return copy.deepcopy(st.session_state.get(_SCENARIOS, {}))


def save_scenario(name: str) -> None:
    """Save the assumptions in force under ``name`` (replacing a scenario of that name)."""
    name = name.strip()
    if not name:
        raise ValueError("A scenario needs a name.")
    saved = dict(st.session_state.get(_SCENARIOS, {}))
    saved[name] = assumptions()
    st.session_state[_SCENARIOS] = saved


# ---------------------------------------------------------------- review decisions


def decisions() -> pd.DataFrame:
    """Review decisions made this session, in the PRD 4.5 file format (a copy)."""
    frame = st.session_state.get(_DECISIONS)
    if frame is None:
        return validate_decisions(None)
    return frame.copy()


def record_decision(
    pair_id: str,
    pair_type: str,
    decision: str,
    pack_qty: float | None = None,
    note: str = "",
) -> None:
    """Record (or replace) the decision on ``pair_id`` and run ``apply_decisions``.

    Decisions are keyed by the stable pair id, never by row position (PRD 9.3).
    A new decision on the same pair replaces the old one and becomes the last.
    """
    row = {
        "pair_id": pair_id,
        "type": pair_type,
        "decision": decision,
        "pack_qty": pack_qty,
        "note": note or None,
        "decided_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    new = validate_decisions(pd.DataFrame([row], columns=list(DECISION_COLUMNS)))
    previous = decisions()
    kept = previous[previous["pair_id"] != pair_id]
    st.session_state[_DECISIONS] = validate_decisions(
        pd.concat([kept, new], ignore_index=True) if not kept.empty else new
    )
    _bump("decisions")
    try:
        current_results()
    except ValueError:
        st.session_state[_DECISIONS] = previous
        _bump("decisions")
        raise


def undo_last_decision() -> None:
    """Remove the most recent decision (PRD 6.5 undo); nothing happens when there is none."""
    previous = decisions()
    if previous.empty:
        return
    st.session_state[_DECISIONS] = validate_decisions(previous.iloc[:-1])
    _bump("decisions")


# ---------------------------------------------------------------- data source


def is_demo() -> bool:
    """True while the session shows the committed demo results."""
    return st.session_state.get(_UPLOADED) is None


def set_uploaded_results(results: Results) -> None:
    """Switch the session to results built from uploaded files (session memory only).

    Decisions and assumption overrides made on the previous data are cleared:
    they refer to other records.
    """
    if results.synergy_cache is None:
        results = replace(results, synergy_cache=results.cached_synergy())
    st.session_state[_UPLOADED] = results
    _clear_work()


def reset_to_demo() -> None:
    """ "Back to demo": drop uploaded results and this session's decisions and overrides."""
    st.session_state.pop(_UPLOADED, None)
    _clear_work()


def _clear_work() -> None:
    for key in (_ASSUMPTIONS, _DECISIONS, _MATCHED, _CURRENT):
        st.session_state.pop(key, None)
    _bump("base", "decisions", "assumptions")
