"""Page scaffolding every screen uses (PRD 6.1, 6.3, 6.13).

A screen is: the question it answers (``page_question``), a finding headline
(``components.style.headline``), one main chart, supporting detail, and one
closing ``next_question`` link. The state blocks give empty, loading, error,
missing-data and not-in-this-view states one look and one wording pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st
from streamlit.errors import StreamlitAPIException

from components.style import esc, headline, muted
from tieout.views import Unavailable

__all__ = [
    "empty_state",
    "error_state",
    "loading_state",
    "missing_data",
    "next_question",
    "page_question",
    "render_placeholder",
    "section",
    "unavailable",
]


def page_question(text: str) -> None:
    """The screen's headline question (PRD 6.3), set small above its finding headline."""
    st.markdown(f'<div class="to-question">{esc(text)}</div>', unsafe_allow_html=True)


def section(text: str, caption: str | None = None) -> None:
    """A section heading in the sans face, with an optional one-line caption."""
    st.markdown(f'<div class="to-section">{esc(text)}</div>', unsafe_allow_html=True)
    if caption:
        st.caption(esc(caption))


def next_question(text: str, target_module: str) -> None:
    """The single closing link of a screen (PRD 6.1 principle 3, 6.3).

    ``target_module`` is the page module name, for example ``"synergies"``.
    """
    st.divider()
    try:
        st.page_link(f"screens/{target_module}.py", label=text, icon=":material/arrow_forward:")
    except StreamlitAPIException:  # page run on its own, outside the navigation
        muted(f"Next: {text}")


def empty_state(
    title: str,
    message: str,
    *,
    link_text: str | None = None,
    target_module: str | None = None,
    icon: str = ":material/info:",
) -> None:
    """Nothing to show, said plainly, with where to go next (e.g. "Nothing left to review").

    ``icon`` is a Material icon shortcode; a finished task uses ``:material/check_circle:``.
    """
    with st.container(border=True):
        st.markdown(f"{icon} **{esc(title)}**")
        muted(message)
        if link_text and target_module:
            try:
                st.page_link(
                    f"screens/{target_module}.py",
                    label=link_text,
                    icon=":material/arrow_forward:",
                )
            except StreamlitAPIException:
                muted(link_text)


def loading_state(stages: Sequence[str], done: int | None = None) -> None:
    """Staged progress with real counts (PRD 6.13), never a bare spinner.

    ``stages`` are sentences such as "2,480 vendor records"; ``done`` is how
    many are complete (all when omitted).
    """
    finished = len(stages) if done is None else done
    text = " → ".join(esc(s) for s in stages[: max(finished, 1)])
    st.progress(finished / max(len(stages), 1), text=text)


def error_state(what: str, affected: str, fix: str) -> None:
    """An error that says what happened, what it affects in rows and dollars, and what to do."""
    st.error(f"**{esc(what)}** {esc(affected)} {esc(fix)}", icon=":material/error:")


def missing_data(message: str) -> None:
    """A feature switched off for lack of optional data, with what would switch it on."""
    st.info(esc(message), icon=":material/info:")


def unavailable(value: Unavailable) -> None:
    """A view's ``Unavailable`` (not in this view mode, or not in the data), shown quietly."""
    st.info(esc(value.message), icon=":material/visibility_off:")


def render_placeholder(question: str, milestone: str) -> None:
    headline(question)
    muted(f"Coming in milestone {milestone}.")
