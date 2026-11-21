"""The review queue (PRD 4.5, 6.5): one candidate at a time, decided with one key.

Layout: the queue on the left (largest dollars at stake first), the candidate in focus on the
right with both records side by side, differing tokens highlighted, the evidence, the stake
line and Approve / Reject / Defer (A, R, D), Undo (Z), and a bulk-approve action with its dollar
effect shown first. Decisions go through ``components.state``; every figure is a view's.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st

from components import state
from components.page import empty_state, error_state, unavailable
from components.plotting import selected_row
from components.style import esc
from tieout import theme as t
from tieout.views import (
    Unavailable,
    bulk_approve_preview,
    headline,
    review_item,
    review_progress,
    review_queue_items,
    thousands,
)

QUEUE_ROWS = 100  # rows of the queue list drawn at once; the focus follows the top of it
_UNDO = "_mt_undo"  # sizes of the actions taken, newest last (a bulk approval is one action)
_EPOCH = "_mt_epoch"  # bumped on every action so the queue list starts with no selection
_ERROR = "_mt_error"
_ALL = "All types"
_TYPE_NAMES = {
    "vendor_match": "Vendor match",
    "vendor_sibling": "Vendor sibling (same parent)",
    "item_match": "Item match",
    "unit_flag": "Unit-of-measure flag",
    "incoterm": "Incoterm difference",
}
_MEANING = {
    "vendor_match": ("Merge into one legal entity", "Keep as different vendors"),
    "vendor_sibling": ("Keep separate, under one parent", "Leave unrelated"),
    "item_match": ("These are the same item", "Never propose this pair again"),
    "unit_flag": ("This is a real price gap", "Keep the pair out of savings"),
    "incoterm": ("The terms are comparable", "Keep the pair out of savings"),
}
_STAGE_NAMES = {
    "V1": "tax ID (V1)",
    "V2": "exact name (V2)",
    "V4": "fuzzy name score (V4)",
    "I1": "part number (I1)",
    "I2": "attributes (I2)",
    "I3": "text similarity (I3)",
}
_TOKEN = re.compile(r"[A-Z0-9]+(?:[./-][A-Z0-9]+)*", re.IGNORECASE)
_IDENTIFIERS = {"vendor_id", "vendor_tax_id", "item_code", "mpn"}
_FIELD_NAMES = {
    "vendor_id": "Vendor ID",
    "vendor_name": "Name",
    "vendor_tax_id": "Tax ID",
    "vendor_country": "Country",
    "item_code": "Item code",
    "mpn": "Part number",
    "manufacturer": "Manufacturer",
    "item_description": "Description",
    "uom": "Unit of measure",
    "pack_qty": "Pack quantity",
}
_MARK = f"background:{t.AMBER_TINT};border-radius:3px;padding:0 2px"


# ---------------------------------------------------------------- actions


def _action(rows: int) -> None:
    st.session_state[_UNDO] = [*st.session_state.get(_UNDO, []), rows]
    st.session_state[_EPOCH] = st.session_state.get(_EPOCH, 0) + 1
    st.session_state.pop(_ERROR, None)


def _fail(error: ValueError) -> None:
    st.session_state[_ERROR] = str(error)


def _decide(pair_id: str, pair_type: str, decision: str) -> None:
    pack = st.session_state.get(f"mt_pack_{pair_id}") if pair_type == "unit_flag" else None
    pack = float(pack) if pack and decision == "approve" else None
    try:
        state.record_decision(pair_id, pair_type, decision, pack_qty=pack)
    except ValueError as error:
        _fail(error)
        return
    _action(1)


def _bulk(pair_ids: list[str]) -> None:
    try:
        state.record_decisions(pair_ids, "approve", note="bulk approval")
    except ValueError as error:
        _fail(error)
        return
    _action(len(pair_ids))


def _undo() -> None:
    stack = list(st.session_state.get(_UNDO, []))
    if not stack:
        return
    for _ in range(stack.pop()):
        state.undo_last_decision()
    st.session_state[_UNDO] = stack
    st.session_state[_EPOCH] = st.session_state.get(_EPOCH, 0) + 1
    st.session_state.pop(_ERROR, None)


# ---------------------------------------------------------------- pieces


def _highlight(label: object, different: set[str]) -> str:
    """The label as safe HTML with the tokens only one side has marked."""
    text, out, last = str(label or ""), [], 0
    for match in _TOKEN.finditer(text):
        out.append(esc(text[last : match.start()]))
        token = esc(match.group())
        out.append(
            f'<span style="{_MARK}">{token}</span>' if match.group().upper() in different else token
        )
        last = match.end()
    out.append(esc(text[last:]))
    return "".join(out)


def _show(value: object) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)


def _card(
    record: dict[str, Any], other: dict[str, Any], pair_type: str, different: set[str]
) -> str:
    colour = t.ACQUIRER if record["company"] == "acquirer" else t.TARGET
    label_field = "vendor_name" if pair_type.startswith("vendor_") else "item_description"
    rows = []
    for field, value in record["fields"].items():
        shown = _show(value)
        if field == label_field:
            body = _highlight(shown, different)
        else:
            body = esc(shown) or "&ndash;"
            if shown != _show(other["fields"].get(field)):
                body = f'<span style="{_MARK}">{body}</span>'
        if field in _IDENTIFIERS:
            body = f'<span class="to-mono">{body}</span>'
        rows.append(
            f'<div style="display:flex;gap:8px;margin:2px 0"><span class="to-caption" '
            f'style="min-width:120px">{esc(_FIELD_NAMES.get(field, field))}</span>'
            f"<span>{body}</span></div>"
        )
    return (
        f'<div class="to-card" style="border-top:4px solid {colour}">'
        f'<div style="color:{t.INK};font-weight:600;margin-bottom:4px">'
        f"{esc(record['company'].capitalize())}</div>{''.join(rows)}"
        f'<div class="to-caption" style="margin-top:6px">{record["lines"]:,} lines, '
        f"{esc(thousands(record['spend']))} a year</div></div>"
    )


def _bullets(title: str, lines: list[str]) -> None:
    if lines:
        st.markdown(f"**{esc(title)}**")
        st.markdown("\n".join(f"- {esc(line)}" for line in lines))


def _evidence(item: dict[str, Any]) -> None:
    with st.container(border=True):
        stage = _STAGE_NAMES.get(str(item["stage"]), item["stage"])
        score = "" if item["score"] is None else f" with score {item['score']:g}"
        proposed = f"Proposed by {stage}{score}." if stage else "Proposed by a check on prices."
        st.markdown(f"**Evidence.** {esc(proposed)}", unsafe_allow_html=True)
        _bullets("Supports the match", item["evidence_for"])
        _bullets("Argues against", item["evidence_against"])
        if not item["evidence_for"] and not item["evidence_against"] and item["message"]:
            st.markdown(esc(item["message"]))


def _focus(item: dict[str, Any], remaining: int) -> None:
    pair_id, pair_type = item["pair_id"], item["type"]
    st.markdown(
        f'<div class="to-kind">{esc(_TYPE_NAMES.get(pair_type, pair_type))}'
        f" &middot; {remaining:,} left in this view</div>",
        unsafe_allow_html=True,
    )
    different = {t_.upper() for t_ in item["differences"]["only_a"] + item["differences"]["only_b"]}
    first, second = item["records"]
    left, right = st.columns(2)
    left.markdown(_card(first, second, pair_type, different), unsafe_allow_html=True)
    right.markdown(_card(second, first, pair_type, different), unsafe_allow_html=True)
    _evidence(item)
    st.markdown(f"**{esc(item['stake_line'])}**")
    if pair_type == "unit_flag":
        st.number_input(
            "Pack quantity (optional)",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"mt_pack_{pair_id}",
            help="For an unconverted pack, the units in one pack, for example 12 for a box of "
            "12. Approving with a quantity re-runs the comparison in base units.",
        )
    meaning = _MEANING.get(pair_type, ("", ""))
    approve, reject, defer, undo = st.columns(4)
    approve.button(
        "Approve (A)",
        key="mt_approve",
        type="primary",
        shortcut="a",
        width="stretch",
        help=meaning[0],
        on_click=_decide,
        args=(pair_id, pair_type, "approve"),
    )
    reject.button(
        "Reject (X)",  # Streamlit reserves R (rerun)
        key="mt_reject",
        shortcut="x",
        width="stretch",
        help=meaning[1],
        on_click=_decide,
        args=(pair_id, pair_type, "reject"),
    )
    defer.button(
        "Defer (D)",
        key="mt_defer",
        shortcut="d",
        width="stretch",
        help="Leave it for later; it moves to the end of the queue.",
        on_click=_decide,
        args=(pair_id, pair_type, "defer"),
    )
    undo.button(
        "Undo (Z)",
        key="mt_undo",
        shortcut="z",
        width="stretch",
        disabled=not st.session_state.get(_UNDO),
        icon=":material/undo:",
        on_click=_undo,
    )
    st.caption(f"Approve means: {meaning[0].lower()}. Reject means: {meaning[1].lower()}.")


def _list(items: pd.DataFrame) -> int | None:
    shown = items.head(QUEUE_ROWS)
    table = pd.DataFrame(
        {
            "Pair": [
                f"{a}  |  {b}" for a, b in zip(shown["label_a"], shown["label_b"], strict=True)
            ],
            "Status": shown["status"].str.capitalize(),
            "At stake": [thousands(v) for v in shown["dollars_at_stake"]],
        }
    )
    event = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        key=f"mt_queue_{st.session_state.get(_EPOCH, 0)}",
    )
    st.caption(
        f"Largest dollars at stake first; the top {len(shown):,} of {len(items):,} shown. "
        "Select a row to review it out of order."
    )
    return selected_row(event)


def _bulk_panel(mode: str, queue_type: str) -> None:
    results = state.current_results()
    with st.expander("Approve in bulk"):
        types = [k for k in ("vendor_match", "vendor_sibling", "item_match")]
        chosen = st.selectbox(
            "Queue type",
            types,
            index=types.index(queue_type) if queue_type in types else 0,
            format_func=lambda k: _TYPE_NAMES[k],
            key="mt_bulk_type",
        )
        whole = bulk_approve_preview(results, chosen, None, mode)
        if isinstance(whole, Unavailable):
            unavailable(whole)
            return
        scale = 0.01 if whole["score_high"] <= 1.0 else 1.0
        low = float(int(whole["score_low"] / scale) * scale)
        high = float(-(-whole["score_high"] // scale) * scale)
        cut = st.slider(
            f"Approve every pending pair at or above this score ({chosen.split('_')[0]} scale)",
            min_value=low,
            max_value=high,
            value=float(int(whole["score_high"] / scale) * scale),
            step=scale,
            key=f"mt_bulk_cut_{chosen}",
        )
        preview = bulk_approve_preview(results, chosen, cut, mode)
        st.markdown(f"This would approve {esc(preview['text'])}.")
        st.button(
            f"Approve {preview['count']:,} pairs",
            key="mt_bulk_go",
            disabled=preview["count"] == 0,
            on_click=_bulk,
            args=(preview["pair_ids"],),
        )


# ---------------------------------------------------------------- entry


def render_queue() -> None:
    """The whole review section; in the integration-office view, the standard unavailable block."""
    results, mode = state.current_results(), state.view()
    items = review_queue_items(results, None, mode)
    if isinstance(items, Unavailable):
        unavailable(items)
        return
    progress = review_progress(results, mode)
    if isinstance(progress, Unavailable):
        unavailable(progress)
        return
    if error := st.session_state.get(_ERROR):
        error_state(
            "That decision could not be applied.",
            f"{error} Nothing was changed.",
            "Undo the last decision or reload the demo.",
        )
    st.progress(
        min(max(progress["share_cleared"], 0.0), 1.0),
        text=f"{progress['text']} ({progress['decided']:,} decided, "
        f"{progress['pending']:,} pending, {progress['deferred']:,} deferred)",
    )
    top = headline(results, mode)
    st.markdown(
        f'<div class="to-caption">Defensible run-rate saving now: '
        f"base {esc(thousands(top['base']))}, "
        f"range {esc(thousands(top['low']))} to {esc(thousands(top['high']))}. "
        "It updates with every decision.</div>",
        unsafe_allow_html=True,
    )
    if progress["empty"]:
        empty_state(
            "Nothing left to review",
            f"{thousands(progress['dollars_cleared'])} of annual spend was cleared by "
            f"{progress['decided']:,} decisions.",
            link_text="See what it is worth: Synergies",
            target_module="synergies",
        )
        if st.session_state.get(_UNDO):
            st.button("Undo (Z)", key="mt_undo_empty", shortcut="z", on_click=_undo)
        return
    counts = items["type"].value_counts()
    names = {_ALL: f"{_ALL} ({len(items):,})"} | {
        k: f"{_TYPE_NAMES[k]} ({counts[k]:,})" for k in _TYPE_NAMES if k in counts
    }
    queue_type = st.selectbox(
        "Show", list(names), format_func=names.get, key="mt_type", label_visibility="collapsed"
    )
    if queue_type != _ALL:
        items = items[items["type"] == queue_type].reset_index(drop=True)
    items = items.iloc[
        list(items.index[items["status"] == "pending"])
        + list(items.index[items["status"] != "pending"])
    ].reset_index(drop=True)
    left, right = st.columns([2, 3])
    with left:
        picked = _list(items)
        _bulk_panel(mode, queue_type)
    row = picked if picked is not None and picked < len(items) else 0
    with right:
        item = review_item(results, items["pair_id"].iloc[row], mode)
        if isinstance(item, Unavailable):
            unavailable(item)
        else:
            _focus(item, len(items))
