""" "Show working" (PRD 6.6): any figure, one level at a time, down to source rows.

``show_working`` puts the button next to a figure and opens an ``st.dialog``
trace panel; ``render_trace`` draws the same panel inline (under a selected
chart bar). Both read :func:`tieout.views.trace_for` with the session's view
mode: the clean-team view drills to source rows, the integration-office view
stops at category level (the view returns "not available in this view").
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from components import state
from components.plotting import selected_row
from components.style import esc
from tieout.views import Unavailable, thousands, trace_for

__all__ = ["MAX_ROWS", "render_trace", "show_working"]

#: Source rows shown in the panel and in the copy block; the rest are counted.
MAX_ROWS = 500
_PATH = "_trace_path_{key}"  # list of (node or figure id, measure) from the root down
_NONCE = "_trace_nonce_{key}"  # bumps on every move so each level's table starts unselected


def _path(key: str) -> list[tuple[str, str | None]]:
    return list(st.session_state.get(_PATH.format(key=key), []))


def _set_path(key: str, path: list[tuple[str, str | None]]) -> None:
    st.session_state[_PATH.format(key=key)] = path
    nonce = _NONCE.format(key=key)
    st.session_state[nonce] = st.session_state.get(nonce, 0) + 1


def _rerun(in_dialog: bool) -> None:
    if in_dialog:
        st.rerun(scope="fragment")
    st.rerun()


def _components_table(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {"Component": frame["label"].astype(str), "Amount": [thousands(v) for v in frame["amount"]]}
    )


def _rows_block(rows: pd.DataFrame | Unavailable, copy_table: str, key: str) -> None:
    if isinstance(rows, Unavailable):
        st.caption(f"Source rows: {rows.message}")
        return
    if rows.empty:
        return
    shown = rows.head(MAX_ROWS)
    more = len(rows) - len(shown)
    title = f"Source rows ({len(rows):,})" + (f", first {MAX_ROWS:,} shown" if more else "")
    st.markdown(f"**{title}**")
    st.caption(
        "Each row exactly as received, with its file name and row number, "
        "next to its normalised form (columns starting normalised_)."
    )
    st.dataframe(shown, hide_index=True, width="stretch", key=f"{key}_rows")
    lines = copy_table.splitlines()
    block = "\n".join(lines[: MAX_ROWS + 1])
    with st.expander("Copy as table (tab-separated)"):
        st.code(block, language=None)


def render_trace(
    figure_id: str,
    key: str,
    measure: str | None = None,
    *,
    in_dialog: bool = False,
) -> None:
    """The trace panel for ``figure_id``: value, selectable components and source rows.

    Selecting a component opens it (one level down); "Back" returns. The path
    restarts whenever ``figure_id`` or ``measure`` changes.
    """
    path = _path(key)
    if not path or path[0] != (figure_id, measure):
        path = [(figure_id, measure)]
        _set_path(key, path)
    node, node_measure = path[-1]
    results = state.current_results()
    working = trace_for(results, node, measure=node_measure, view=state.view())

    if len(path) > 1 and st.button("Back", key=f"{key}_back", icon=":material/arrow_back:"):
        _set_path(key, path[:-1])
        _rerun(in_dialog)
    if isinstance(working, Unavailable):
        st.info(working.message)
        return

    _header(working, depth=len(path))
    components = working["components"]
    if isinstance(components, Unavailable):
        st.info(f"Below this level: {components.message}")
    elif not components.empty:
        nonce = st.session_state.get(_NONCE.format(key=key), 0)
        st.caption("Select a component to open it.")
        event = st.dataframe(
            _components_table(components),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key=f"{key}_components_{nonce}",
        )
        chosen = selected_row(event)
        if chosen is not None and chosen < len(components):
            child = components.iloc[chosen]["node"]
            if isinstance(child, str) and child:
                _set_path(key, [*path, (child, _child_measure(working["measure"]))])
                _rerun(in_dialog)
            else:
                st.caption("Merged categories cannot be opened in this view.")
    _rows_block(working["rows"], working["copy_table"], key)


def _child_measure(measure: str) -> str | None:
    """A component is opened in its parent's measure, except under the composite run rate,
    whose levers each have their own default measure."""
    return None if measure.startswith("recurring_") else measure


def _header(working: dict[str, Any], depth: int) -> None:
    level = "" if depth == 1 else f" (level {depth})"
    st.markdown(f"**{esc(working['label'])}**{level}: {esc(thousands(working['value']))}")


@st.dialog("Show working", width="large")
def _dialog(figure_id: str, label: str, key: str, measure: str | None) -> None:
    st.caption(esc(label))
    render_trace(figure_id, key, measure, in_dialog=True)


def show_working(figure_path: str, label: str, key: str, measure: str | None = None) -> None:
    """The "Show working" button for one figure; clicking it opens the trace dialog.

    ``figure_path`` is a dotted ``totals`` path or a trace node (the
    ``figure_id`` a view function returns); ``label`` names the figure in the
    dialog; ``key`` must be unique on the page; ``measure`` overrides the
    node's default measure (for example ``raw_1`` for a unit trap).
    """
    if st.button(
        "Show working",
        key=f"show_working_{key}",
        type="tertiary",
        icon=":material/account_tree:",
        help=f"What {label} is made of, down to source rows",
    ):
        _set_path(f"dialog_{key}", [(figure_path, measure)])
        _dialog(figure_path, label, f"dialog_{key}", measure)
