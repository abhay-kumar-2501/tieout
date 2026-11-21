"""The assumption forms of the Assumptions screen (PRD 6.7, 9.3).

One ``st.form`` per group, so a half-edited set of inputs never triggers a
recalculation. Submitting and resetting run as button callbacks, before the
page script, so the header and every figure already show the new answer. A
rejected value shows the message from ``state.set_assumptions`` (or, for
ranges the engine does not check, the screen's own) and changes nothing.

Widget keys carry the value in force, so any change to the assumptions (a
submit, a reset, a scenario, the cap slider elsewhere) starts the inputs afresh.
"""

from __future__ import annotations

import streamlit as st

from components import state
from components.assumptions_spec import (
    GROUPS,
    Field,
    Group,
    changed_paths,
    default_for,
    format_value,
    from_display,
    get_path,
    nested,
    range_error,
    to_display,
)
from components.style import esc

__all__ = ["render_forms", "reset_all", "summary_line"]

_ERROR = "_asm_error_{group}"
_INTEGER_UNITS = ("months", "days", "count")


def _key(field: Field, current: float) -> str:
    return f"asm:{field.dotted}:{to_display(field, current):g}"


def _error_key(group: str) -> str:
    return _ERROR.format(group=group)


def summary_line() -> str:
    """ "4 assumptions changed from default" (PRD 6.7)."""
    count = len(changed_paths(state.assumptions()))
    if count == 0:
        return "All assumptions are at their defaults."
    noun = "assumption" if count == 1 else "assumptions"
    return f"{count} {noun} changed from default."


def _submit(group: Group) -> None:
    current = state.assumptions()
    values: dict[tuple[str, ...], float] = {}
    try:
        for row in group.rows:
            for field in row.fields:
                shown = st.session_state[_key(field, get_path(current, field.path))]
                if shown is None:
                    raise ValueError(f"{field.dotted} needs a number")
                message = range_error(field, shown)
                if message:
                    raise ValueError(message)
                stored = from_display(field, shown)
                values[field.path] = int(stored) if field.unit in _INTEGER_UNITS else stored
        state.set_assumptions(nested(values))
        st.session_state[_error_key(group.id)] = None
    except ValueError as exc:
        st.session_state[_error_key(group.id)] = str(exc)


def _reset_group(group: Group) -> None:
    defaults = {f.path: default_for(f) for r in group.rows for f in r.fields}
    try:
        state.set_assumptions(nested(defaults))
        st.session_state[_error_key(group.id)] = None
    except ValueError as exc:
        st.session_state[_error_key(group.id)] = str(exc)


def reset_all() -> None:
    """Every assumption back to the base run's own (the defaults for the demo)."""
    state.reset_assumptions()
    for group in GROUPS:
        st.session_state[_error_key(group.id)] = None


def _input(field: Field, current: float, changed: bool) -> None:
    shown = to_display(field, current)
    label = f"{field.name} (changed)" if changed else field.name
    if field.unit in _INTEGER_UNITS:
        st.number_input(label, value=int(shown), step=1, format="%d", key=_key(field, current))
    elif field.unit == "usd":
        st.number_input(
            label, value=float(shown), step=1000.0, format="%.0f", key=_key(field, current)
        )
    else:
        st.number_input(
            label, value=float(shown), step=0.5, format="%.2f", key=_key(field, current)
        )


def _range_text(field: Field) -> str:
    if field.unit == "pct":
        return "0% to 100%"
    return f"{field.low:g} to {format_value(field, field.high)}"


def _group(group: Group, current_all: dict) -> None:
    changed = {f.dotted for f in changed_paths(current_all)}
    with st.container(border=True):
        top, button = st.columns([5, 1], vertical_alignment="center")
        with top:
            st.markdown(f"**{esc(group.title)}**")
            st.caption(esc(group.blurb))
        with button:
            st.button(
                "Reset group",
                key=f"asm_reset_{group.id}",
                type="tertiary",
                icon=":material/restart_alt:",
                on_click=_reset_group,
                args=(group,),
            )
        with st.form(f"asm_form_{group.id}", border=False):
            for row in group.rows:
                st.markdown(esc(row.title))
                columns = st.columns(len(row.fields))
                for column, field in zip(columns, row.fields, strict=True):
                    with column:
                        _input(field, get_path(current_all, field.path), field.dotted in changed)
                first = row.fields[0]
                defaults = ", ".join(
                    format_value(f, default_for(f))
                    if len(row.fields) == 1
                    else f"{f.name} {format_value(f, default_for(f))}"
                    for f in row.fields
                )
                st.caption(
                    esc(f"{row.explanation} Default: {defaults}. Valid: {_range_text(first)}.")
                )
            st.form_submit_button(
                "Apply changes",
                type="primary",
                on_click=_submit,
                args=(group,),
                key=f"asm_apply_{group.id}",
            )
        message = st.session_state.get(_error_key(group.id))
        if message:
            st.error(esc(message), icon=":material/error:")


def render_forms() -> None:
    """Every group as its own form, with its reset and any rejection message."""
    current = state.assumptions()
    for group in GROUPS:
        _group(group, current)
