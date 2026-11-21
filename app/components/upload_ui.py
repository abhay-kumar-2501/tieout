"""The "Use your own data" stepper (PRD 2.3): Upload, Map columns, Validate, Map categories, Run.

Uploaded bytes and everything derived from them live in ``st.session_state``
only (PRD 9.3): nothing is written to disk, logged or cached across sessions.
Step logic is in ``components.upload_steps`` and the engine in ``tieout.upload``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from components import state
from components.page import error_state, loading_state
from components.style import esc
from components.upload_steps import (
    COMPANY_LABELS,
    STEPS,
    Facts,
    advance,
    blockers,
    stale_after,
    step_status,
)
from tieout import upload
from tieout.ingest import BlockingValidationError, FileLimitError, UnreadableFileError
from tieout.ingest.schema import COLUMNS, REQUIRED
from tieout.reference import load_taxonomy
from tieout.views import money, thousands

__all__ = ["is_active", "leave", "render_upload_flow", "start"]

ACTIVE = "_up_active"
STEP = "_up_step"
_KEYS = {
    "files": "_up_files",
    "mapping": "_up_mapping",
    "check": "_up_check",
    "categories": "_up_categories",
    "run_error": "_up_run_error",
    "catfile": "_up_catfile",
    "cat_round": "_up_cat_round",
}
_WIDGET_PREFIXES = ("up_map_", "up_file_", "up_cat_")
_NOT_USED = ""
PRIVACY = (
    "The public demo is not a place for real deal data. Run the tool locally for that. "
    "Files you add here are held in this session's memory only: they are never written "
    "to disk or logged, and they are gone when the session ends."
)
LIMITS = (
    f"Each file may have up to {upload.MAX_ROWS:,} rows and {upload.MAX_BYTES // 2**20} MB, "
    "as CSV or XLSX (first sheet)."
)


# ---------------------------------------------------------------- state


def is_active() -> bool:
    return bool(st.session_state.get(ACTIVE))


def _clear_widgets(*prefixes: str) -> None:
    for key in [k for k in st.session_state if str(k).startswith(prefixes or _WIDGET_PREFIXES)]:
        del st.session_state[key]


def start() -> None:
    """Switch the session to upload mode at the first step."""
    leave()
    st.session_state[ACTIVE] = True
    st.session_state[STEP] = 0


def leave() -> None:
    """Drop every upload-flow value (files included) and leave upload mode."""
    for key in (ACTIVE, STEP, "_up_round", *_KEYS.values()):
        st.session_state.pop(key, None)
    _clear_widgets()


def _drop(names: tuple[str, ...]) -> None:
    for name in names:
        st.session_state.pop(_KEYS[name], None)
    if "mapping" in names:
        _clear_widgets("up_map_")
    if "categories" in names:
        _clear_widgets("up_cat_")
        for extra in ("catfile", "cat_round"):
            st.session_state.pop(_KEYS[extra], None)


def _facts() -> Facts:
    categories = st.session_state.get(_KEYS["categories"])
    mapped = 0 if categories is None else int((categories["l2_code"].fillna("") != "").sum())
    return Facts(
        files=st.session_state.get(_KEYS["files"], {}),
        mapping=st.session_state.get(_KEYS["mapping"], {}),
        check=st.session_state.get(_KEYS["check"]),
        mapped_categories=mapped,
    )


# ---------------------------------------------------------------- frame


def _stepper(current: int) -> None:
    marks = {"done": "✓", "current": "●", "todo": "○"}
    labels = [
        f"<b>{marks[s]} {i + 1}. {esc(label)}</b>"
        if s == "current"
        else f"{marks[s]} {i + 1}. {esc(label)}"
        for i, (label, s) in enumerate(step_status(current))
    ]
    st.markdown(
        '<div class="to-muted">' + " &nbsp;›&nbsp; ".join(labels) + "</div>", unsafe_allow_html=True
    )


def render_upload_flow() -> None:
    """The whole stepper: progress strip, the current step and Back / Continue."""
    step = int(st.session_state.get(STEP, 0))
    top, spacer = st.columns([1, 4])
    if top.button("Back to demo", key="up_back_to_demo", icon=":material/undo:"):
        leave()
        state.reset_to_demo()
        st.rerun()
    _stepper(step)
    st.write("")
    (_step_upload, _step_columns, _step_validate, _step_categories, _step_run)[step]()
    _navigation(step)


def _navigation(step: int) -> None:
    facts = _facts()
    stop = blockers(step, facts)
    left, right, _ = st.columns([1, 1, 4])
    if left.button("Back", key="up_prev", disabled=step == 0):
        st.session_state[STEP] = step - 1
        st.rerun()
    if step < len(STEPS) - 1:
        if right.button("Continue", key="up_next", type="primary", disabled=bool(stop)):
            st.session_state[STEP] = advance(step, facts)
            st.rerun()
        for reason in stop:
            if not (step == 2 and facts.check is not None and facts.check.blocked):
                st.caption(esc(reason))


# ---------------------------------------------------------------- step 1: upload


def _store_file(company: str, uploaded: Any) -> None:
    files = dict(st.session_state.get(_KEYS["files"], {}))
    if uploaded is None:  # an empty uploader keeps the stored file; "Remove" drops it
        return
    if company in files and files[company]["file_id"] == uploaded.file_id:
        return
    data = uploaded.getvalue()
    label = COMPANY_LABELS[company]
    try:
        peek = upload.peek_file(data, uploaded.name)
    except (FileLimitError, UnreadableFileError) as exc:
        error_state(
            f"The {label.lower()} file was refused.",
            str(exc),
            "Split the file, or reduce it, and add it again.",
        )
        files.pop(company, None)
        st.session_state[_KEYS["files"]] = files
        return
    files[company] = {
        "file_id": uploaded.file_id,
        "name": uploaded.name,
        "data": data,
        "headers": peek.headers,
        "rows": peek.rows,
        "size": peek.size,
    }
    st.session_state[_KEYS["files"]] = files
    _drop(stale_after(0))


def _remove_file(company: str) -> None:
    files = dict(st.session_state.get(_KEYS["files"], {}))
    files.pop(company, None)
    st.session_state[_KEYS["files"]] = files
    st.session_state["_up_round"] = st.session_state.get("_up_round", 0) + 1  # a fresh uploader
    _drop(stale_after(0))


def _step_upload() -> None:
    st.info(PRIVACY, icon=":material/lock:")
    st.caption(esc(LIMITS))
    columns = st.columns(2)
    for column, (company, label) in zip(columns, COMPANY_LABELS.items(), strict=True):
        with column:
            uploaded = st.file_uploader(
                f"{label} purchasing file",
                type=["csv", "xlsx"],
                key=f"up_file_{company}_{st.session_state.get('_up_round', 0)}",
            )
            _store_file(company, uploaded)
            info = st.session_state.get(_KEYS["files"], {}).get(company)
            if info:
                st.caption(
                    esc(
                        f"Using {info['name']}: {info['rows']:,} rows, "
                        f"{info['size'] / 2**20:.1f} MB, {len(info['headers'])} columns."
                    )
                )
                if st.button("Remove file", key=f"up_file_remove_{company}"):
                    _remove_file(company)
                    st.rerun()


# ---------------------------------------------------------------- step 2: columns


def _init_mapping(files: Mapping[str, Mapping[str, Any]]) -> None:
    """Put the suggestions into the selectboxes the first time the step is shown."""
    stored = st.session_state.get(_KEYS["mapping"], {})
    for company, info in files.items():
        suggestions = upload.suggest_columns(info["headers"])
        info["suggestions"] = suggestions
        for i, s in enumerate(suggestions):
            key = f"up_map_{company}_{i}"
            if key not in st.session_state:  # widget state is dropped while another step shows
                kept = stored.get(company, {}).get(info["headers"][i], s.field)
                st.session_state[key] = kept or _NOT_USED


def _field_label(field: str) -> str:
    if field == _NOT_USED:
        return "Not used"
    return f"{field} (required)" if field in REQUIRED else field


def _step_columns() -> None:
    files = st.session_state.get(_KEYS["files"], {})
    _init_mapping(files)
    st.markdown(
        "Each of your column headers is matched to a Tie-Out field. Check the suggestions and "
        "correct any that are wrong. Fields marked required must be mapped."
    )
    mapping: dict[str, dict[str, str | None]] = {}
    for company, label in COMPANY_LABELS.items():
        info = files[company]
        chosen: dict[str, str | None] = {}
        with st.expander(f"{label} file: {len(info['headers'])} columns", expanded=True):
            for i, (header, s) in enumerate(zip(info["headers"], info["suggestions"], strict=True)):
                how = {
                    "exact": "Recognised name.",
                    "fuzzy": f"Close match (score {s.score:.0f}); please check.",
                    "none": "No match found.",
                }[s.method]
                value = st.selectbox(
                    header,
                    [_NOT_USED, *COLUMNS],
                    key=f"up_map_{company}_{i}",
                    format_func=_field_label,
                    help=how,
                )
                chosen[header] = value or None
        mapping[company] = chosen
    if mapping != st.session_state.get(_KEYS["mapping"]):
        _drop(stale_after(1))
        st.session_state[_KEYS["mapping"]] = mapping


# ---------------------------------------------------------------- step 3: validate


def _run_check() -> None:
    files = st.session_state[_KEYS["files"]]
    rows = " and ".join(f"{files[c]['rows']:,}" for c in COMPANY_LABELS)
    with st.status(f"Checking {rows} rows against the schema", expanded=False) as status:
        try:
            check = upload.check_upload(
                files["acquirer"]["data"],
                files["target"]["data"],
                st.session_state[_KEYS["mapping"]],
            )
        except (FileLimitError, UnreadableFileError, ValueError) as exc:
            status.update(label="The files could not be checked", state="error")
            st.session_state[_KEYS["run_error"]] = str(exc)
            return
        status.update(label=f"Checked {rows} rows", state="complete")
    st.session_state[_KEYS["check"]] = check
    st.session_state.pop(_KEYS["run_error"], None)


def _findings_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Company": frame["company"].str.capitalize(),
            "Finding": frame["message"],
            "Rows": frame["rows"],
            "Value affected": [thousands(a) for a in frame["amount"]],
            "What to do": frame["fix"],
        }
    )


def _step_validate() -> None:
    if _KEYS["check"] not in st.session_state and _KEYS["run_error"] not in st.session_state:
        _run_check()
    problem = st.session_state.get(_KEYS["run_error"])
    if problem:
        error_state("The files could not be checked.", problem, "Go back and correct the mapping.")
        return
    check = st.session_state[_KEYS["check"]]
    findings = check.findings
    blocking = findings[findings["severity"] == "blocking"]
    if blocking.empty:
        st.success(
            f"No blocking errors. {sum(check.rows.values()):,} rows read, "
            f"{money(check.spend)} of annual spend in scope.",
            icon=":material/check_circle:",
        )
    for row in blocking.itertuples():
        error_state(
            f"{row.company.capitalize()}: {row.message}",
            f"{row.rows:,} rows, {thousands(row.amount)} affected.",
            row.fix,
        )
    if check.blocked:
        st.caption("Go back, correct the file or the mapping, and add it again to continue.")
    for severity, title in (("warning", "Warnings"), ("info", "Notes")):
        part = findings[findings["severity"] == severity]
        if not part.empty:
            amount = thousands(float(part["amount"].sum()))
            with st.expander(f"{title}: {len(part)} (up to {amount} affected)"):
                st.dataframe(_findings_frame(part), hide_index=True, width="stretch")


# ---------------------------------------------------------------- step 4: categories


def _options() -> dict[str, str]:
    taxonomy = load_taxonomy()
    return {
        f"{r.l2_code}  {r.l2_name}": r.l2_code for r in taxonomy.sort_values("l2_code").itertuples()
    }


def _category_file(table: pd.DataFrame) -> pd.DataFrame:
    """Optionally apply a ``category_map.csv`` (PRD 3.2) on top of the suggestions."""
    with st.expander("Have a category map file? Load it instead of editing by hand"):
        st.caption("A CSV with the columns company, category_native, l2_code.")
        uploaded = st.file_uploader("Category map (CSV)", type=["csv"], key="up_cat_file")
        if uploaded is None or st.session_state.get(_KEYS["catfile"]) == uploaded.file_id:
            return table
        st.session_state[_KEYS["catfile"]] = uploaded.file_id
        try:
            table, applied, skipped = upload.apply_category_file(table, uploaded.getvalue())
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
            return table
        st.session_state[_KEYS["categories"]] = table
        round_key = _KEYS["cat_round"]
        st.session_state[round_key] = st.session_state.get(round_key, 0) + 1  # drop old edits
        st.session_state["_up_cat_note"] = f"The file set {applied} categories" + (
            f"; {skipped} rows did not apply." if skipped else "."
        )
        st.rerun()
    return table


def _step_categories() -> None:
    check = st.session_state[_KEYS["check"]]
    options = _options()
    by_code = {code: label for label, code in options.items()}
    if _KEYS["categories"] not in st.session_state:
        st.session_state[_KEYS["categories"]] = check.suggestions.copy()
    table = st.session_state[_KEYS["categories"]]
    st.markdown(
        "Each native category is matched to the common taxonomy by comparing its words with each "
        "common category's keywords. Suggestions below 30% overlap are left unmapped. Change any "
        "that are wrong; unmapped spend counts but cannot be matched."
    )
    table = _category_file(table)
    view = pd.DataFrame(
        {
            "Company": table["company"].str.capitalize(),
            "Your category": table["category_native"],
            "Annual spend": table["spend"].round(0),
            "Overlap": table["score"].round(2),
            "Common category": table["l2_code"].map(by_code).fillna(""),
        }
    )
    edited = st.data_editor(
        view,
        hide_index=True,
        width="stretch",
        key=f"up_cat_editor_{st.session_state.get(_KEYS['cat_round'], 0)}",
        disabled=["Company", "Your category", "Annual spend", "Overlap"],
        column_config={
            "Annual spend": st.column_config.NumberColumn(format="$%d"),
            "Common category": st.column_config.SelectboxColumn(
                options=["", *options], required=False
            ),
        },
    )
    codes = edited["Common category"].map(lambda label: options.get(label, ""))
    updated = table.copy()
    updated["l2_code"] = codes.to_numpy()
    st.session_state[_KEYS["categories"]] = updated
    total = float(updated["spend"].sum())
    mapped = float(updated.loc[updated["l2_code"] != "", "spend"].sum())
    count = int((updated["l2_code"] != "").sum())
    if note := st.session_state.pop("_up_cat_note", None):
        st.info(note, icon=":material/info:")
    st.caption(
        esc(
            f"{count} of {len(updated)} categories mapped, covering {mapped / total:.0%} of spend."
            if total
            else "No spend."
        )
    )


# ---------------------------------------------------------------- step 5: run


def _progress_text(seen: dict[str, Mapping[str, Any]]) -> list[str]:
    stages = []
    ingest = seen.get("ingest")
    if ingest:
        rows = ingest["rows"]
        stages.append(
            f"{rows['acquirer'] + rows['target']:,} rows → {ingest['lines']:,} lines in scope → "
            f"{ingest['vendor_records']:,} vendor records"
        )
    vendors = seen.get("vendor_matching")
    if vendors:
        stages.append(
            f"{vendors['after_normalisation']:,} after normalisation → "
            f"{vendors['legal_entities']:,} after matching"
        )
    items = seen.get("item_matching")
    if items:
        stages.append(
            f"{items['records']:,} item records → {items['matchable_records']:,} in mapped "
            f"categories → {items['canonical_items']:,} canonical items"
        )
    if "synergy" in seen:
        stages.append("savings calculated")
    return stages


def _step_run() -> None:
    files = st.session_state[_KEYS["files"]]
    st.markdown(
        f"Ready to match {files['acquirer']['rows'] + files['target']['rows']:,} rows: vendors "
        "first, then items, then the savings. Uncertain matches go to the review queue."
    )
    error = st.session_state.get(_KEYS["run_error"])
    if error:
        error_state("Matching stopped.", error, "Go back and check the mapping.")
    if not st.button("Run matching", key="up_run", type="primary", icon=":material/play_arrow:"):
        return
    seen: dict[str, Mapping[str, Any]] = {}
    slot = st.empty()
    total = 4

    def show(stage: str, counts: Mapping[str, Any]) -> None:
        seen[stage] = counts
        with slot.container():
            loading_state([*_progress_text(seen), *[""] * (total - len(seen))][:total], len(seen))

    with slot.container():
        st.progress(0.0, text="Reading and validating the files")
    try:
        results = upload.run_upload(
            files["acquirer"]["data"],
            files["target"]["data"],
            st.session_state[_KEYS["mapping"]],
            st.session_state[_KEYS["categories"]],
            names={c: files[c]["name"] for c in files},
            progress=show,
        )
    except BlockingValidationError:
        st.session_state[_KEYS["run_error"]] = "Validation found blocking errors."
        st.rerun()
        return
    except ValueError as exc:
        st.session_state[_KEYS["run_error"]] = str(exc)
        st.rerun()
        return
    state.set_uploaded_results(results)
    leave()  # the raw files are dropped from memory; only the results stay
    st.rerun()
