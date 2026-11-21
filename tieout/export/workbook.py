"""The workbook export (PRD 7.1): formula-live, built in memory, clean or masked.

:func:`build_workbook` returns the ``.xlsx`` bytes. Every figure on
``Summary`` and ``Bridge`` is a formula over the detail tabs, and each formula
carries the engine's own result as its stored value, so the file reads
correctly in viewers that do not recalculate.

**Clean-team workbook: the formula chain.** The assumptions are named input
cells on ``Assumptions``; ``Category_Settings`` takes each category's
effective value from them (or holds the category's own override as an input).
The levers then run in sequence on the declining baseline, as the engine does:

1. ``Opportunities``, lever-1 rows: gross gap ``G1`` (a value) x the capture
   probability looked up in ``Category_Settings`` (PRD 5.2).
2. ``Links`` (left table): the share of each lever-1 opportunity's saving that
   rests on a lever-2 category's eligible spend (a value per pair) x that
   saving. Lever-2 rows on ``Opportunities`` hold the post-move spend and
   ``f`` as values and deduct those savings with ``SUMIFS``:
   ``B2 = IF(f > 0, MAX(post-move spend - lever-1 saving, 0), 0)`` and
   ``N2 = B2 x d x pi2`` (PRD 5.3).
3. ``Links`` (right table): the lever-1 savings and each category's lever-2
   saving that fall on a vendor group's retained spend; ``Payment_Terms``
   deducts them, ``S = MAX(retained spend - deductions, 0)`` and
   ``cash = gap days / 365 x S x pi3``; lever-3 rows sum their vendor's groups
   (PRD 5.4).
4. Switching costs per opportunity ``= (fixed x switch-event share + pct x
   spend moved) x capture probability``; phasing multiplies run-rate by the
   stored months-active shares, or by the named ramp cells on the global ramp
   (PRD 5.6).

Recurring savings (levers 1 and 2) and one-time cash (lever 3) sit in
separate columns and are never added together. The tables never refer to a
range that depends on themselves, so Excel sees no circular reference.

**Integration-office (masked) workbook** (PRD 6.9, 7.1): vendor codes,
categories with fewer than three parent vendors merged into "Other", no unit
prices, items or source rows. Its detail tabs are aggregated values taken
from the masked view functions; ``Summary`` and ``Bridge`` are formulas over
those aggregated tabs.
"""

from __future__ import annotations

import datetime as dt
import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

from tieout import theme
from tieout.synergy.assemble import RE_TENDER
from tieout.synergy.cube import SpendCube
from tieout.synergy.lever1 import CASES, STEP_NAMES, Filters, lever1
from tieout.synergy.lever2 import ONE_COMPANY, lever2
from tieout.synergy.lever3 import DAYS_PER_YEAR, lever3
from tieout.synergy.phasing import GLOBAL_RAMP, QUARTERS, quarter_factors, start_quarter
from tieout.synergy.settings import CategoryParams, category_table, number_cell
from tieout.synergy.stage import (
    _category_params,
    _lever1_setup,
    _scatter,
    _settings,
    _switch_groups,
    _switch_lines,
    close_date,
)
from tieout.synergy.trace import line_contributions
from tieout.views.charts import concentration, phasing_by_quarter, phasing_by_year
from tieout.views.common import (
    CLEAN,
    MASKED,
    Unavailable,
    category_label,
    category_labels,
    item_labels,
    parent_labels,
    resolve_view,
)
from tieout.views.overview import headline, opportunity_labels
from tieout.views.tables import CANNOT_SEE, data_quality_summary, scorecard_table

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "CHECK_NAME",
    "CLEAN_SHEETS",
    "MASKED_SHEETS",
    "SUMMARY_NAMES",
    "build_workbook",
]

CLEAN_SHEETS = (
    "README",
    "Summary",
    "Assumptions",
    "Bridge",
    "Bridge_Detail",
    "Category_Settings",
    "Opportunities",
    "Links",
    "Spend_Cube",
    "Price_Variance",
    "Payment_Terms",
    "Risk",
    "Phasing",
    "Vendor_Map",
    "Item_Map",
    "Review_Log",
    "Scorecard",
    "Data_Quality",
)
MASKED_SHEETS = (
    "README",
    "Summary",
    "Assumptions",
    "Bridge",
    "Bridge_By_Category",
    "Category_Settings",
    "Opportunities",
    "Spend_Cube",
    "Risk",
    "Phasing",
    "Scorecard",
    "Data_Quality",
)
CHECK_NAME = "Check_TieOut"
_CASE_TITLE = {"low": "Low", "base": "Base", "high": "High"}
_HEADER_ROW = 4  # 0-based: tables start on Excel row 5, data on row 6
_INPUT_BLUE = "#0000FF"
_TABLE_STYLE = "Table Style Light 1"
_ANYWHERE = "A1:XFD1048576"


# ---------------------------------------------------------------- public entry point


def build_workbook(results: Results, view: str | None = None) -> bytes:
    """The workbook as ``.xlsx`` bytes, built in memory (never written to disk).

    ``view`` is ``"clean"`` or ``"masked"``; omitted, the run's own view mode.
    """
    mode = resolve_view(results, view)
    engine = _engine(results)
    book = _Book(results, mode)
    if mode == CLEAN:
        _build_clean(book, engine)
    else:
        _build_masked(book, engine)
    return book.close()


# ---------------------------------------------------------------- engine working


@dataclass(frozen=True)
class _Engine:
    """The engine's intermediate figures the formulas start from (one evaluation).

    ``lever2_links``: ``target`` (``L2:{l2}``), ``kind`` (``capped`` /
    ``uncapped``), ``source`` (lever-1 opportunity id), ``coef``: the share of
    the source's saving resting on the target category's lever-2 base.
    ``lever3_links``: ``group`` (row of ``payment_terms``), ``source``
    (lever-1 or lever-2 opportunity id), ``coef``. ``retained`` is each
    vendor group's spend net of lever-2 moves (gaining groups only).
    """

    settings: dict[str, Any]
    method: str
    cube: SpendCube
    params: CategoryParams
    addressable_l2: frozenset[str]
    post_move: dict[str, tuple[float, float]]
    post_move_uncapped: dict[str, tuple[float, float]]
    lever2_links: pd.DataFrame
    lever3_links: pd.DataFrame
    retained: np.ndarray
    gap_days: np.ndarray
    event_share: dict[str, float]
    spend_moved: dict[str, float]


def _link_frame(
    keys: Sequence[Any], sources: np.ndarray, x: np.ndarray, gross: pd.Series
) -> pd.DataFrame:
    """``(key, source) -> sum(x) / gross[source]``: a share of the source's saving."""
    if not len(x):
        return pd.DataFrame(
            {
                "key": pd.Series(dtype=object),
                "source": pd.Series(dtype=object),
                "coef": pd.Series(dtype=float),
            }
        )
    frame = pd.DataFrame({"key": list(keys), "source": sources, "x": x})
    summed = frame.groupby(["key", "source"], sort=True)["x"].sum().reset_index()
    summed["coef"] = summed["x"] / summed["source"].map(gross).to_numpy(dtype=float)
    return summed[["key", "source", "coef"]]


def _engine(results: Results) -> _Engine:
    """Re-run the assumption-dependent arithmetic once to read its linear working.

    Every saving is a capture probability times a fixed gross amount, so each
    downstream base is a fixed share of upstream savings; the shares are what
    the workbook stores as values (see the module docstring).
    """
    cache = results.cached_synergy()
    settings = _settings(results.assumptions)
    setup = _lever1_setup(cache, settings)
    inputs, lines, cube = setup.inputs, setup.lines, cache.cube
    cases = {case: lever1(inputs, Filters(), case, settings) for case in CASES}
    gross = lever1(inputs, Filters(capture_probability=False), "base", settings)
    group_opp = results.price_groups["opportunity_id"].to_numpy(dtype=object)
    if len(group_opp) != len(inputs.groups):
        raise ValueError("results.price_groups does not match the results' own synergy inputs")
    l1 = {c: _scatter(cache, line_contributions(inputs, lines, cases[c])) for c in CASES}
    gross_line = _scatter(cache, line_contributions(inputs, lines, gross))
    switch = _switch_groups(inputs, gross, cases["base"])
    switch_lines = _switch_lines(cache, setup, switch)
    params = _category_params(cache, settings)
    lev2 = lever2(cube, params, l1, switch_lines, settings)
    uncapped = lever2(cube, params, l1, switch_lines, settings, cap=np.ones_like(params.cap))
    lev3 = lever3(
        cube,
        l1,
        lev2,
        settings,
        enabled=all(cube.has_terms_data.values()),
        observed_allowed=not bool(cache.meta.get("aggregated", False)),
    )
    n = len(cube)
    line_opp = np.full(n, None, dtype=object)
    line_opp[cache.tagged_rows] = group_opp[lines.group]
    opps = results.opportunities
    gross_by_opp = pd.Series(
        opps["gross_gap"].to_numpy(dtype=float), index=opps["opportunity_id"].to_numpy()
    )
    codes = np.array(cube.l2_codes, dtype=object)
    l2_ids = np.array(["L2:" + c for c in cube.l2_codes] + [None], dtype=object)
    line_l2_id = l2_ids[np.where(cube.mapped, cube.l2, len(cube.l2_codes))]

    def lever2_links(result: Any, kind: str) -> pd.DataFrame:
        x = result.weight * gross_line
        keep = np.flatnonzero(x != 0)
        frame = _link_frame(line_l2_id[keep], line_opp[keep], x[keep], gross_by_opp)
        return frame.rename(columns={"key": "target"}).assign(kind=kind)

    links2 = pd.concat(
        [lever2_links(lev2, "capped"), lever2_links(uncapped, "uncapped")], ignore_index=True
    )

    # lever 3: retained spend and the savings that fall on it, per gaining vendor group
    groups = lev3.groups
    n_groups = len(groups)
    t_star = groups["T_star"].to_numpy(dtype=float)
    t_now = groups["T"].to_numpy(dtype=float)
    gap = np.maximum(np.nan_to_num(t_star - t_now, nan=0.0), 0.0) if n_groups else np.zeros(0)
    member = lev3.line_group >= 0
    gains = member & (np.append(gap, 0.0)[np.where(member, lev3.line_group, n_groups)] > 0)
    rows = lev3.line_group[gains]
    retained = np.bincount(rows, weights=(cube.amount - lev2.moved)[gains], minlength=n_groups)
    moved_share = np.where(lev2.moved != 0, lev2.weight, 0.0)
    x1 = np.where(gains, (1.0 - moved_share) * gross_line, 0.0)
    keep1 = np.flatnonzero(x1 != 0)
    links_l1 = _link_frame(lev3.line_group[keep1], line_opp[keep1], x1[keep1], gross_by_opp)
    c_line = cube.per_line(lev2.C)
    qualifies = cube.per_line(lev2.qualifies) & cube.mapped & (c_line > 0) & gains
    keep2 = np.flatnonzero(qualifies)
    share = cube.amount[keep2] / c_line[keep2]
    ones = pd.Series(1.0, index=pd.Index(l2_ids[:-1]))
    links_l2 = _link_frame(lev3.line_group[keep2], line_l2_id[keep2], share, ones)
    links3 = pd.concat([links_l1, links_l2], ignore_index=True).rename(columns={"key": "group"})

    event_share, spend_moved = _switch_events(cache, setup, cases["base"], switch, lev2, group_opp)
    addressable = frozenset(
        str(c) for c, r in zip(codes, lev2.reason, strict=True) if r != ONE_COMPANY
    )
    return _Engine(
        settings=settings,
        method=str(results.totals["phasing"]["method"]),
        cube=cube,
        params=params,
        addressable_l2=addressable,
        post_move={
            str(c): (float(lev2.P_eligible[i] + lev2.f[i] * lev2.M[i]), float(lev2.f[i]))
            for i, c in enumerate(codes)
        },
        post_move_uncapped={
            str(c): (
                float(uncapped.P_eligible[i] + uncapped.f[i] * uncapped.M[i]),
                float(uncapped.f[i]),
            )
            for i, c in enumerate(codes)
        },
        lever2_links=links2,
        lever3_links=links3,
        retained=retained,
        gap_days=gap,
        event_share=event_share,
        spend_moved=spend_moved,
    )


def _switch_events(
    cache: Any, setup: Any, base: Any, switch: np.ndarray, lev2: Any, group_opp: np.ndarray
) -> tuple[dict[str, float], dict[str, float]]:
    """Per opportunity: its share of switch events and the spend it moves (PRD 5.6).

    Mirrors :func:`tieout.synergy.assemble.build_costs`, whose cost per moved
    dollar is ``(fixed x moved / event moved + pct x moved) x pi``.
    """
    cube, tagged, lines = cache.cube, cache.tagged, setup.lines
    g = setup.inputs.groups
    group = lines.group
    moving1 = switch[group] & tagged["def_ok"].to_numpy(dtype=bool) & lines.open
    holder = base.holder_group[group]
    dest1 = np.where(holder >= 0, g["parent_id"].to_numpy()[np.clip(holder, 0, None)], RE_TENDER)
    rows1 = cache.tagged_rows[moving1]
    n = len(cube)
    moved = np.zeros(n)
    moved[rows1] = tagged["amount"].to_numpy()[moving1]
    lev2_rows = np.flatnonzero(lev2.moved != 0)
    moved[lev2_rows] = lev2.moved[lev2_rows]
    codes = np.array(cube.l2_codes, dtype=object)
    opportunity = np.full(n, None, dtype=object)
    opportunity[rows1] = group_opp[group[moving1]]
    opportunity[lev2_rows] = ["L2:" + str(c) for c in codes[cube.l2[lev2_rows]]]
    category = np.full(n, None, dtype=object)
    category[rows1] = g["l2_code"].to_numpy()[group[moving1]]
    category[lev2_rows] = codes[cube.l2[lev2_rows]]
    dest = np.full(n, None, dtype=object)
    dest[rows1] = dest1[moving1]
    dest[lev2_rows] = np.array(cube.parents, dtype=object)[lev2.preferred[cube.l2[lev2_rows]]]
    moving = np.flatnonzero(pd.notna(opportunity))
    if not len(moving):
        return {}, {}
    keys = (
        pd.Series(cube.company[moving], dtype=object)
        + "|"
        + pd.Series(category[moving], dtype=object).astype(str)
        + "|"
        + pd.Series(dest[moving], dtype=object).astype(str)
    )
    event_codes, events = pd.factorize(keys, sort=True)
    event_moved = np.bincount(event_codes, weights=moved[moving], minlength=len(events))
    per = event_moved[event_codes]
    share = np.where(per > 0, moved[moving] / np.where(per > 0, per, 1.0), 0.0)
    frame = pd.DataFrame({"opp": opportunity[moving], "share": share, "moved": moved[moving]})
    summed = frame.groupby("opp", sort=True)[["share", "moved"]].sum()
    return summed["share"].to_dict(), summed["moved"].to_dict()


# ---------------------------------------------------------------- cells and tables


@dataclass(frozen=True)
class _F:
    """A formula cell and the engine's value for it."""

    formula: str
    value: Any


@dataclass(frozen=True)
class _In:
    """An input value (blue font)."""

    value: Any


@dataclass(frozen=True)
class Col:
    """One table column: data key, header text, number format kind and width."""

    key: str
    header: str
    kind: str = "text"
    width: float | None = None


_NUMBER_FORMATS = {
    "text": None,
    "int": "#,##0",
    "money": "#,##0;(#,##0);0",
    "price": "#,##0.0000;(#,##0.0000)",
    "share": "0.0%",
    "factor": "0.0000",
    "num": "#,##0.00;(#,##0.00)",
    "days": "0.0",
    "date": "yyyy-mm-dd",
}
_WIDTHS = {
    "text": 16,
    "int": 10,
    "money": 14,
    "price": 13,
    "share": 10,
    "factor": 9,
    "num": 11,
    "days": 9,
    "date": 12,
}


@dataclass(frozen=True)
class _Table:
    """Where a written table sits, to build A1 references to it."""

    sheet: str
    header_row: int
    first_col: int
    keys: tuple[str, ...]
    n: int

    def col(self, key: str) -> int:
        return self.first_col + self.keys.index(key)

    def letter(self, key: str) -> str:
        return xl_col_to_name(self.col(key))

    def row(self, i: int) -> int:
        """Excel (1-based) row number of data row ``i``."""
        return self.header_row + 2 + i

    def rng(self, key: str) -> str:
        """The column's data rows, sheet-qualified and absolute."""
        letter = self.letter(key)
        return f"{self.sheet}!${letter}${self.row(0)}:${letter}${self.row(self.n - 1)}"

    def here(self, key: str, i: int) -> str:
        """The cell of data row ``i`` in ``key``, as a same-sheet reference."""
        return f"${self.letter(key)}{self.row(i)}"

    def at(self, key: str, i: int) -> str:
        """The cell of data row ``i`` in ``key``, sheet-qualified and absolute."""
        return f"{self.sheet}!${self.letter(key)}${self.row(i)}"


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float | np.floating):
        return not math.isfinite(float(value))
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _cached(value: Any) -> Any:
    """A formula's stored result: a finite number, a string, or 0."""
    if isinstance(value, str):
        return value
    if _blank(value):
        return 0
    return float(value)


class _Book:
    """The XlsxWriter workbook with the shared formats and sheet furniture."""

    def __init__(self, results: Results, mode: str) -> None:
        self.results = results
        self.mode = mode
        self.buffer = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buffer, {"in_memory": True})
        created = _report_datetime(results)
        self.wb.set_properties(
            {"title": "Tie-Out synergy workbook", "author": "Tie-Out", "created": created}
        )
        self._formats: dict[tuple[str, str], Any] = {}
        self.sheets: dict[str, Any] = {}
        meta = results.meta
        self.illustrative = meta.get("scenario") == "demo" or meta.get("seed") is not None
        self.names: dict[str, str] = {}

    def close(self) -> bytes:
        self.wb.close()
        return self.buffer.getvalue()

    def fmt(self, kind: str = "text", role: str = "data") -> Any:
        key = (kind, role)
        if key not in self._formats:
            spec: dict[str, Any] = {"font_name": theme.EXPORT_FONT_BODY, "font_size": 10}
            number = _NUMBER_FORMATS.get(kind)
            if number:
                spec["num_format"] = number
            if role == "input":
                spec["font_color"] = _INPUT_BLUE
            elif role == "fixed":
                spec["font_color"] = theme.MUTED
            elif role == "formula":
                spec["font_color"] = "#000000"
            elif role == "total":
                spec |= {"bold": True, "top": 1}
            elif role == "title":
                spec |= {"font_name": theme.EXPORT_FONT_TITLE, "font_size": 16, "bold": True}
                spec["font_color"] = theme.INK
            elif role == "label":
                spec |= {"bold": True, "font_color": theme.INK}
            elif role == "note":
                spec |= {"italic": True, "font_color": theme.MUTED}
            elif role == "section":
                spec |= {"bold": True, "font_size": 11, "font_color": theme.TEAL, "bottom": 1}
            elif role == "banner":
                tint = theme.AMBER_TINT if self.mode == MASKED else theme.TEAL_TINT
                spec |= {"bg_color": tint, "font_color": theme.INK, "bold": True}
            elif role == "check":
                spec |= {"bold": True, "bg_color": theme.TEAL_TINT, "border": 1, "align": "center"}
            elif role == "head":
                spec |= {"bold": True, "bottom": 1, "text_wrap": True, "valign": "bottom"}
            self._formats[key] = self.wb.add_format(spec)
        return self._formats[key]

    def add_sheets(self, names: Sequence[str]) -> None:
        for name in names:
            self.sheets[name] = self.wb.add_worksheet(name)

    def furnish(self, name: str, title: str, note: str = "") -> Any:
        """A1 label, title, view banner and a one-line note on sheet ``name``."""
        ws = self.sheets[name]
        ws.hide_gridlines(2)
        first = theme.ILLUSTRATIVE_LABEL if self.illustrative else "Tie-Out"
        ws.write_string(0, 0, first, self.fmt("text", "note"))
        ws.write_string(1, 0, title, self.fmt("text", "title"))
        ws.write_string(2, 0, _banner(self.mode), self.fmt("text", "banner"))
        if note:
            ws.write_string(3, 0, note, self.fmt("text", "note"))
        ws.ignore_errors(
            {
                "formula_differs": _ANYWHERE,
                "calculated_column": _ANYWHERE,
                "number_stored_as_text": _ANYWHERE,
            }
        )
        ws.set_column(0, 0, 18)
        return ws

    def define(self, name: str, sheet: str, row: int, col: int) -> None:
        """Defined name ``name`` for the 0-based cell ``(row, col)`` on ``sheet``."""
        ref = f"{sheet}!${xl_col_to_name(col)}${row + 1}"
        self.wb.define_name(name, f"={ref}")
        self.names[name] = ref

    def write_value(self, ws: Any, row: int, col: int, value: Any, kind: str, role: str) -> None:
        fmt = self.fmt(kind, role)
        if isinstance(value, _F):
            ws.write_formula(
                row, col, value.formula, self.fmt(kind, "formula"), _cached(value.value)
            )
        elif isinstance(value, _In):
            self.write_value(ws, row, col, value.value, kind, "input")
        elif _blank(value):
            return
        elif isinstance(value, bool | np.bool_):
            ws.write_string(row, col, "Yes" if value else "No", fmt)
        elif isinstance(value, str):
            ws.write_string(row, col, value, fmt)
        elif isinstance(value, int | float | np.integer | np.floating):
            ws.write_number(row, col, float(value), fmt)
        elif isinstance(value, pd.Timestamp | dt.date):
            ws.write_string(row, col, pd.Timestamp(value).strftime("%Y-%m-%d"), fmt)
        else:
            ws.write_string(row, col, str(value), fmt)

    def table(
        self,
        sheet: str,
        name: str,
        cols: Sequence[Col],
        data: Mapping[str, Sequence[Any]],
        *,
        header_row: int = _HEADER_ROW,
        first_col: int = 0,
        freeze: bool = True,
    ) -> _Table:
        """An Excel table with frozen headers and filters; cells may be ``_F`` / ``_In``.

        A table with no rows keeps one blank data row so that every range
        stays valid.
        """
        ws = self.sheets[sheet]
        lengths = {len(data[c.key]) for c in cols}
        if len(lengths) > 1:
            raise ValueError(f"{sheet}: columns of different lengths {sorted(lengths)}")
        rows = lengths.pop() if lengths else 0
        n = max(rows, 1)
        ws.add_table(
            header_row,
            first_col,
            header_row + n,
            first_col + len(cols) - 1,
            {
                "name": name,
                "style": _TABLE_STYLE,
                "columns": [{"header": c.header} for c in cols],
            },
        )
        for j, col in enumerate(cols):
            c = first_col + j
            ws.set_column(c, c, col.width or _WIDTHS[col.kind])
            for i, value in enumerate(data[col.key]):
                self.write_value(ws, header_row + 1 + i, c, value, col.kind, "data")
        if freeze:
            ws.freeze_panes(header_row + 1, 0)
        return _Table(sheet, header_row, first_col, tuple(c.key for c in cols), n)


def _report_datetime(results: Results) -> dt.datetime:
    """A fixed creation time (the report date) so the same results give the same file."""
    text = results.meta.get("report_date")
    try:
        return pd.Timestamp(text).to_pydatetime() if text else dt.datetime(2026, 1, 1)
    except (TypeError, ValueError):
        return dt.datetime(2026, 1, 1)


def _banner(mode: str) -> str:
    if mode == MASKED:
        return (
            "Integration-office view: vendor names are codes, results are aggregated to "
            "category level, unit prices and items are hidden. A presentation mode, not a "
            "security control."
        )
    return "Clean-team view: full detail, including vendor names and unit prices."


def _column(frame: pd.DataFrame, key: str) -> list[Any]:
    if key not in frame.columns:
        return [None] * len(frame)
    values = frame[key].astype(object).tolist()
    return [None if _blank(v) else v for v in values]


def _frame_data(frame: pd.DataFrame, cols: Sequence[Col]) -> dict[str, list[Any]]:
    return {c.key: _column(frame, c.key) for c in cols}


# ---------------------------------------------------------------- assumptions


@dataclass(frozen=True)
class _Assumption:
    name: str
    path: tuple[str, ...]
    label: str
    explanation: str
    kind: str
    live: bool


def _triples(prefix: str, path: tuple[str, ...], what: str, effect: str) -> list[_Assumption]:
    return [
        _Assumption(
            f"{prefix}_{_CASE_TITLE[case]}",
            (*path, case),
            f"{what}, {case} case",
            effect,
            "share",
            True,
        )
        for case in CASES
    ]


_ASSUMPTIONS: tuple[_Assumption, ...] = (
    *_triples(
        "Pi1_Same",
        ("lever1", "same_vendor"),
        "Lever 1 capture probability, same vendor",
        "Share of a same-vendor price gap won in negotiation; higher raises lever 1 "
        "and slightly lowers the lever-2 and lever-3 bases.",
    ),
    *_triples(
        "Pi1_Switch",
        ("lever1", "switch"),
        "Lever 1 capture probability, vendor switch",
        "Share of a gap that needs a vendor switch won; higher raises lever 1.",
    ),
    *_triples(
        "Pi2",
        ("lever2", "capture"),
        "Lever 2 capture probability",
        "Share of the expected volume discount won; higher raises lever 2.",
    ),
    *[
        _Assumption(
            f"Discount_{label.replace(' ', '_')}",
            ("lever2", "discount", key),
            f"Volume discount, {label.lower()} categories",
            "Expected price improvement from the larger combined volume; higher raises lever 2.",
            "share",
            True,
        )
        for key, label in (
            ("commodity", "Commodity"),
            ("engineered", "Engineered"),
            ("mro", "MRO"),
            ("indirect", "Indirect"),
        )
    ],
    *_triples(
        "Pi3",
        ("lever3", "capture"),
        "Lever 3 capture probability",
        "Share of the longer payment terms won; higher raises the one-time cash release.",
    ),
    *[
        _Assumption(
            f"Ramp_Year{y}",
            ("global_ramp", f"year{y}"),
            f"Global ramp, year {y}",
            f"Share of run-rate realised in year {y} when no contract dates exist; "
            "higher raises realised savings (used on the global ramp only).",
            "share",
            True,
        )
        for y in (1, 2, 3)
    ],
    _Assumption(
        "Cost_Of_Capital",
        ("cost_of_capital",),
        "Cost of capital",
        "Values the cash release as an annual financing benefit; higher raises that memo "
        "line only, never the savings.",
        "share",
        True,
    ),
    _Assumption(
        "Switch_Cost_Fixed",
        ("switching_cost", "fixed_usd"),
        "Switching cost per switch event",
        "Qualification and onboarding per vendor that receives spend; higher raises one-time cost.",
        "money",
        True,
    ),
    _Assumption(
        "Switch_Cost_Pct",
        ("switching_cost", "pct_of_spend_moved"),
        "Switching cost, share of spend moved",
        "Cost per dollar of spend moved to a new vendor; higher raises one-time cost.",
        "share",
        True,
    ),
    *[
        _Assumption(
            f"Band_{name}_{end.title()}",
            ("reference_bands", key, end),
            f"Reference band, {words}, {end}",
            "A sanity check for the base case, not a target; it changes no saving.",
            "share",
            True,
        )
        for key, name, words in (
            ("total_spend", "Total", "share of total spend"),
            ("addressable_spend", "Addressable", "share of addressable spend"),
        )
        for end in ("low", "high")
    ],
    _Assumption(
        "Planning_Horizon_Months",
        ("planning_horizon_months",),
        "Planning horizon (months)",
        "Volume under contract beyond it is locked in; longer counts more volume. Re-run "
        "in the tool to change.",
        "int",
        False,
    ),
    _Assumption(
        "Max_Payment_Days",
        ("lever3", "max_payment_days"),
        "Maximum payment terms (days)",
        "Caps the target terms; higher can raise the cash release. Re-run in the tool.",
        "int",
        False,
    ),
    *[
        _Assumption(
            f"Cap_{label.replace(' ', '_')}",
            ("caps", key),
            f"Concentration cap, {label.lower()} categories",
            "Largest share one parent vendor may hold after consolidation; higher moves more "
            "spend. Re-run in the tool.",
            "share",
            False,
        )
        for key, label in (
            ("critical", "Critical"),
            ("standard", "Standard"),
            ("non_critical", "Non critical"),
        )
    ],
    _Assumption(
        "Benchmark_Min_Share",
        ("benchmark", "min_volume_share"),
        "Benchmark volume test",
        "Share of an item's volume a group needs to set the benchmark price; lower admits "
        "spot buys. Re-run in the tool.",
        "share",
        False,
    ),
    _Assumption(
        "Benchmark_Min_Lines",
        ("benchmark", "min_lines"),
        "Benchmark line test",
        "Purchase lines a group needs to set the benchmark price. Re-run in the tool.",
        "int",
        False,
    ),
    *[
        _Assumption(
            f"Lead_{label}",
            ("lead_time_months", key),
            f"Lead time, {words} (months)",
            "Months from availability to the first saving; longer delays phasing. Re-run in "
            "the tool.",
            "int",
            False,
        )
        for key, label, words in (
            ("l1_same_vendor", "L1_Same_Vendor", "lever 1 same vendor"),
            ("l1_switch", "L1_Switch", "lever 1 vendor switch"),
            ("l2", "L2", "lever 2"),
            ("l3", "L3", "lever 3"),
        )
    ],
)


def _lookup(tree: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = tree
    for key in path:
        node = node[key]
    return node


def _write_assumptions(book: _Book, engine: _Engine, live: bool) -> None:
    """Every input in a named cell; the arithmetic ones recalculate the workbook."""
    sheet = "Assumptions"
    note = (
        "Blue cells are inputs: changing one recalculates the workbook. Grey values are fixed "
        "settings that decide which rows qualify; change them in the tool and re-run."
    )
    if not live:
        note = (
            "The integration-office workbook holds aggregated values: only the financing memo "
            "and the reference-band checks recalculate here. Use the clean-team workbook to "
            "test assumptions."
        )
    ws = book.furnish(sheet, "Assumptions", note)
    heads = ("Name", "Assumption", "Value", "Recalculates", "What it does")
    for j, head in enumerate(heads):
        ws.write_string(_HEADER_ROW, j, head, book.fmt("text", "head"))
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 44)
    ws.set_column(2, 2, 14)
    ws.set_column(3, 3, 13)
    ws.set_column(4, 4, 90)
    row = _HEADER_ROW + 1
    settings = engine.settings
    for item in _ASSUMPTIONS:
        value = float(_lookup(settings, item.path))
        role = "input" if item.live else "fixed"
        ws.write_string(row, 0, item.name, book.fmt())
        ws.write_string(row, 1, item.label, book.fmt())
        ws.write_number(row, 2, value, book.fmt(item.kind, role))
        ws.write_string(row, 3, "Yes" if item.live else "No: re-run", book.fmt())
        ws.write_string(row, 4, item.explanation, book.fmt())
        book.define(item.name, sheet, row, 2)
        row += 1
    close = close_date(settings, book.results.meta)
    thresholds = book.results.meta.get("thresholds") or {}
    fixed_text = [
        ("Close_Date", "Close date", close.strftime("%Y-%m-%d") if close is not None else ""),
        ("Phasing_Method", "Phasing method", engine.method.replace("_", " ")),
    ]
    for key, label in (
        ("vendor_auto", "Vendor match, automatic threshold"),
        ("vendor_review", "Vendor match, review threshold"),
        ("item_auto_cosine", "Item match, automatic cosine"),
        ("item_review_cosine", "Item match, review cosine"),
    ):
        if key in thresholds:
            fixed_text.append((f"Threshold_{key.title().replace('_', '')}", label, thresholds[key]))
    for name, label, value in fixed_text:
        ws.write_string(row, 0, name, book.fmt())
        ws.write_string(row, 1, label, book.fmt())
        book.write_value(
            ws, row, 2, value, "num" if not isinstance(value, str) else "text", "fixed"
        )
        ws.write_string(row, 3, "No: re-run", book.fmt())
        ws.write_string(row, 4, "Recorded for reference; re-run in the tool to change.", book.fmt())
        book.define(name, sheet, row, 2)
        row += 1
    ws.freeze_panes(_HEADER_ROW + 1, 0)


# ---------------------------------------------------------------- category settings


_PI_COLUMNS = [f"pi2_{c}" for c in CASES] + [
    f"pi1_{change}_{c}" for change in ("same", "switch") for c in CASES
]
_PI_NAMES = {f"pi2_{c}": f"Pi2_{_CASE_TITLE[c]}" for c in CASES} | {
    f"pi1_{change}_{c}": f"Pi1_{change.title()}_{_CASE_TITLE[c]}"
    for change in ("same", "switch")
    for c in CASES
}
_DISCOUNT_NAMES = {
    "commodity": "Discount_Commodity",
    "engineered": "Discount_Engineered",
    "mro": "Discount_MRO",
    "indirect": "Discount_Indirect",
}


@dataclass(frozen=True)
class _Settings:
    """``Category_Settings`` and each category's effective values."""

    table: _Table
    index: dict[str, int]
    values: dict[str, dict[str, float]]

    def lookup(self, code: Any, column: str, key_cell: str) -> str | None:
        """``INDEX/MATCH`` into the column for the code in ``key_cell``; None when absent."""
        if code is None or str(code) not in self.index:
            return None
        return f"INDEX({self.table.rng(column)},MATCH({key_cell},{self.table.rng('l2_code')},0))"


def _effective_settings(engine: _Engine) -> dict[str, dict[str, float]]:
    params, settings = engine.params, engine.settings
    table = category_table(settings.get("category_settings"))
    out = {}
    for i, code in enumerate(params.l2_codes):
        row = table.get(code, {})
        values = {"cap": float(params.cap[i]), "d": float(params.d[i])}
        values |= {f"pi2_{c}": float(params.pi2[c][i]) for c in CASES}
        for change, key in (("same", "same_vendor"), ("switch", "switch")):
            for c in CASES:
                own = number_cell(row.get(f"pi1_{change}_{c}"))
                default = float(settings["lever1"][key][c])
                values[f"pi1_{change}_{c}"] = default if math.isnan(own) else own
        out[code] = values
    return out


def _write_category_settings(book: _Book, engine: _Engine) -> _Settings:
    """One row per L2 category: inherited values link to the named assumptions."""
    sheet = "Category_Settings"
    book.furnish(
        sheet,
        "Category settings",
        "Each category's effective values. Black formulas follow the global assumption; blue "
        "values are this category's own override. Caps are fixed (re-run to change).",
    )
    params, settings = engine.params, engine.settings
    overrides = category_table(settings.get("category_settings"))
    labels = category_labels(book.results, CLEAN)
    values = _effective_settings(engine)
    codes = list(params.l2_codes)
    data: dict[str, list[Any]] = {
        "l2_code": codes,
        "category": [category_label(labels, c) for c in codes],
        "criticality": [str(c) for c in params.criticality],
        "category_type": [None if t is None else str(t) for t in params.category_type],
        "cap": [values[c]["cap"] for c in codes],
    }
    data["d"] = []
    for code, ctype in zip(codes, params.category_type, strict=True):
        own = number_cell(overrides.get(code, {}).get("d"))
        if not math.isnan(own):
            data["d"].append(_In(own))
        elif ctype in _DISCOUNT_NAMES:
            data["d"].append(_F(_DISCOUNT_NAMES[str(ctype)], values[code]["d"]))
        else:
            data["d"].append(_In(values[code]["d"]))
    for column in _PI_COLUMNS:
        cells = []
        for code in codes:
            own = number_cell(overrides.get(code, {}).get(column))
            if math.isnan(own):
                cells.append(_F(_PI_NAMES[column], values[code][column]))
            else:
                cells.append(_In(own))
        data[column] = cells
    cols = [
        Col("l2_code", "L2 code", width=10),
        Col("category", "Category", width=34),
        Col("criticality", "Criticality", width=12),
        Col("category_type", "Category type", width=13),
        Col("cap", "Concentration cap (fixed)", "share"),
        Col("d", "Volume discount d", "share"),
        *[Col(f"pi2_{c}", f"Lever 2 capture {c}", "share") for c in CASES],
        *[Col(f"pi1_same_{c}", f"Lever 1 same vendor {c}", "share") for c in CASES],
        *[Col(f"pi1_switch_{c}", f"Lever 1 switch {c}", "share") for c in CASES],
    ]
    table = book.table(sheet, "CategorySettings", cols, data)
    return _Settings(table, {c: i for i, c in enumerate(codes)}, values)


# ---------------------------------------------------------------- opportunities (clean)


def _opportunity_pi(
    opps: pd.DataFrame, engine: _Engine, values: Mapping[str, Mapping[str, float]]
) -> dict[str, np.ndarray]:
    """Capture probability per opportunity and case, as the engine applies it."""
    settings = engine.settings
    out = {}
    for case in CASES:
        pis = []
        for lever, code, change in zip(
            opps["lever"], opps["l2_code"], opps["change_type"], strict=True
        ):
            if lever == 1:
                key = "same" if change == "same_vendor" else "switch"
                full = "same_vendor" if key == "same" else "switch"
                row = values.get(str(code)) if code is not None else None
                pis.append(row[f"pi1_{key}_{case}"] if row else settings["lever1"][full][case])
            elif lever == 2:
                pis.append(values[str(code)][f"pi2_{case}"])
            else:
                pis.append(float(settings["lever3"]["capture"][case]))
        out[case] = np.array(pis, dtype=float)
    return out


def _opportunity_costs(
    opps: pd.DataFrame, engine: _Engine, pi: Mapping[str, np.ndarray]
) -> dict[str, np.ndarray]:
    cost = engine.settings["switching_cost"]
    fixed, pct = float(cost["fixed_usd"]), float(cost["pct_of_spend_moved"])
    share = opps["opportunity_id"].map(engine.event_share).fillna(0.0).to_numpy(dtype=float)
    moved = opps["opportunity_id"].map(engine.spend_moved).fillna(0.0).to_numpy(dtype=float)
    return {case: (fixed * share + pct * moved) * pi[case] for case in CASES}


def _case_cols(prefix: str, header: str, kind: str = "money") -> list[Col]:
    return [Col(f"{prefix}_{c}", header.format(case=c), kind) for c in CASES]


_OPP_COLS: tuple[Col, ...] = (
    Col("no", "No.", "int", 6),
    Col("opportunity_id", "Opportunity", width=28),
    Col("lever", "Lever", "int", 6),
    Col("change_type", "Change type", width=13),
    Col("l2_code", "L2 code", width=9),
    Col("category", "Category", width=28),
    Col("subject", "Item or vendor", width=36),
    Col("vendor", "Vendor", width=24),
    Col("parent_id", "Parent id", width=14),
    Col("status", "Status", width=13),
    Col("tier", "Item tier", width=7),
    Col("vendor_tier", "Vendor tier", width=7),
    Col("gross_gap", "Gross gap", "money"),
    Col("post_move", "L2 post-move spend", "money"),
    Col("f", "L2 moved fraction f", "factor"),
    *_case_cols("deduct", "L2 lever-1 deduction {case}"),
    *_case_cols("b2", "L2 base B2 {case}"),
    Col("d", "L2 discount d", "share"),
    *_case_cols("pi", "Capture probability {case}", "share"),
    *_case_cols("l1", "Price saving {case} (lever 1)"),
    *_case_cols("l2", "Volume saving {case} (lever 2)"),
    *_case_cols("l3", "Cash release {case} (lever 3, one-time)"),
    Col("upside", "Upside pending review (base)", "money"),
    Col("post_move_uncapped", "L2 post-move spend, cap 100%", "money"),
    Col("f_uncapped", "L2 f, cap 100%", "factor"),
    Col("deduct_uncapped", "L2 lever-1 deduction, cap 100% (base)", "money"),
    Col("forgone", "Savings forgone (base)", "money"),
    Col("event_share", "Switch events", "factor"),
    Col("spend_moved", "Spend moved", "money"),
    *_case_cols("cost", "One-time cost {case}"),
    Col("available_month", "Available month", "int"),
    Col("start_month", "Start month", "int"),
    Col("start_quarter", "Start quarter", "int"),
    Col("start_year", "Start year", "int"),
    Col("sites", "Sites affected", "int"),
    Col("complexity", "Complexity", "num"),
    Col("wave", "Wave", "int", 6),
    *[Col(f"q{q}", f"Q{q} share", "factor") for q in range(1, QUARTERS + 1)],
    *[Col(f"y{y}", f"Year {y} share", "factor") for y in (1, 2, 3)],
)
_LINK2_COLS: tuple[Col, ...] = (
    Col("target_no", "Lever-2 opportunity no.", "int", 10),
    Col("target", "Lever-2 opportunity", width=16),
    Col("kind", "Cap", width=10),
    Col("source_no", "Lever-1 opportunity no.", "int", 10),
    Col("source", "Lever-1 opportunity", width=26),
    Col("coef", "Share of saving", "factor", 10),
    *_case_cols("v", "Lever-1 saving in base {case}"),
)
_LINK3_COLS: tuple[Col, ...] = (
    Col("target_no", "Payment-terms group no.", "int", 10),
    Col("target", "Vendor group", width=26),
    Col("source_no", "Opportunity no.", "int", 10),
    Col("source", "Opportunity", width=26),
    Col("source_lever", "Lever", "int", 6),
    Col("coef", "Share of saving", "factor", 10),
    *_case_cols("v", "Saving on retained spend {case}"),
)
_LINK3_FIRST_COL = len(_LINK2_COLS) + 1
_PT_COLS: tuple[Col, ...] = (
    Col("no", "No.", "int", 6),
    Col("parent_id", "Parent id", width=14),
    Col("vendor", "Vendor", width=26),
    Col("company", "Company", width=10),
    Col("status", "Status", width=14),
    Col("basis", "Basis", width=9),
    Col("reason", "Reason excluded", width=30),
    Col("T", "Current days T", "days"),
    Col("T_star", "Target days T*", "days"),
    Col("gap_days", "Days gained", "days"),
    Col("spend", "Annual spend", "money"),
    Col("coverage", "Payment-date coverage", "share"),
    Col("retained", "Spend retained after lever 2", "money"),
    *_case_cols("deduct", "Savings deducted {case}"),
    *_case_cols("s", "Spend S {case}"),
    *_case_cols("cash", "Cash release {case}"),
    Col("gross", "Cash before capture", "money"),
    Col("opp_no", "Opportunity no.", "int", 10),
)


@dataclass(frozen=True)
class _Layout:
    """Where the inter-dependent clean tables sit, fixed before any is written."""

    opp: _Table
    links2: _Table
    links3: _Table
    pt: _Table
    numbers: dict[str, int]


def _layout(results: Results, engine: _Engine) -> _Layout:
    opps = results.opportunities
    numbers = {str(o): i + 1 for i, o in enumerate(opps["opportunity_id"])}

    def table(sheet: str, cols: Sequence[Col], n: int, first_col: int = 0) -> _Table:
        return _Table(sheet, _HEADER_ROW, first_col, tuple(c.key for c in cols), max(n, 1))

    return _Layout(
        opp=table("Opportunities", _OPP_COLS, len(opps)),
        links2=table("Links", _LINK2_COLS, len(engine.lever2_links)),
        links3=table("Links", _LINK3_COLS, len(engine.lever3_links), _LINK3_FIRST_COL),
        pt=table("Payment_Terms", _PT_COLS, len(results.payment_terms)),
        numbers=numbers,
    )


def _case_values(opps: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Opportunity id -> engine low / base / high."""
    ids = opps["opportunity_id"].astype(str).tolist()
    return {c: dict(zip(ids, opps[c].astype(float).tolist(), strict=True)) for c in CASES}


def _weighted(links: pd.DataFrame, values: Mapping[str, float]) -> float:
    """``sum(coef x values[source])`` over link rows."""
    pairs = zip(links["coef"].tolist(), links["source"].tolist(), strict=True)
    return float(sum(coef * values[source] for coef, source in pairs))


def _forgone(results: Results, code: str) -> float:
    risk = results.category_risk
    rows = risk.loc[risk["l2_code"] == code, "savings_forgone"]
    return float(rows.iloc[0]) if len(rows) else 0.0


def _write_opportunities(book: _Book, engine: _Engine, cs: _Settings, lay: _Layout) -> _Table:
    """One row per opportunity, low / base / high as formulas (see the module docstring)."""
    sheet = "Opportunities"
    book.furnish(
        sheet,
        "Opportunities",
        "Price and volume savings are recurring; cash release is one-time and is never added "
        "to them. Lever-2 bases deduct lever-1 savings through Links; lever-3 rows sum "
        "Payment_Terms.",
    )
    results = book.results
    opps = results.opportunities.reset_index(drop=True)
    n = len(opps)
    pi = _opportunity_pi(opps, engine, cs.values)
    costs = _opportunity_costs(opps, engine, pi)
    labels = category_labels(results, CLEAN)
    names = parent_labels(results, CLEAN)
    subjects = opportunity_labels(results, opps, CLEAN) if n else []
    starts = opps["start_month"].to_numpy(dtype=np.int64)
    quarters = start_quarter(starts) if n else np.zeros(0, dtype=np.int64)
    recurring = (opps["lever"] != 3).to_numpy()
    ramp = engine.settings["global_ramp"]
    factors = quarter_factors(starts, engine.method, ramp) if n else np.zeros((0, QUARTERS))
    factors = np.where(recurring[:, None], factors, 0.0)
    values = _case_values(opps)
    link2, l2t, pt, opp = engine.lever2_links, lay.links2, lay.pt, lay.opp
    data: dict[str, list[Any]] = {c.key: [None] * n for c in _OPP_COLS}
    for i, row in enumerate(opps.itertuples(index=False)):
        lever, oid, code = int(row.lever), str(row.opportunity_id), row.l2_code
        r = opp.row(i)

        def here(key: str, _r: int = r) -> str:
            return f"${opp.letter(key)}{_r}"

        data["no"][i] = i + 1
        data["opportunity_id"][i] = oid
        data["lever"][i] = lever
        data["change_type"][i] = row.change_type
        data["l2_code"][i] = code
        data["category"][i] = category_label(labels, code)
        data["subject"][i] = subjects[i]
        data["parent_id"][i] = row.parent_id
        data["vendor"][i] = names.get(row.parent_id) if isinstance(row.parent_id, str) else None
        data["status"][i] = row.status
        data["tier"][i] = row.tier
        data["vendor_tier"][i] = row.vendor_tier
        for c in CASES:
            if lever == 1:
                column = f"pi1_{'same' if row.change_type == 'same_vendor' else 'switch'}_{c}"
                formula = cs.lookup(code, column, here("l2_code")) or _PI_NAMES[column]
            elif lever == 2:
                formula = cs.lookup(code, f"pi2_{c}", here("l2_code")) or _PI_NAMES[f"pi2_{c}"]
            else:
                formula = f"Pi3_{_CASE_TITLE[c]}"
            data[f"pi_{c}"][i] = _F(formula, pi[c][i])
        if lever == 1:
            data["gross_gap"][i] = float(row.gross_gap)
            in_range = row.status == "in_range"
            for c in CASES:
                data[f"l1_{c}"][i] = (
                    _F(f"{here('gross_gap')}*{here('pi_' + c)}", values[c][oid])
                    if in_range
                    else 0.0
                )
            data["upside"][i] = (
                0.0
                if in_range
                else _F(f"{here('gross_gap')}*{here('pi_base')}", float(row.upside_base))
            )
        elif lever == 2:
            post, frac = engine.post_move[str(code)]
            post_u, frac_u = engine.post_move_uncapped[str(code)]
            data["post_move"][i], data["f"][i] = post, frac
            data["post_move_uncapped"][i], data["f_uncapped"][i] = post_u, frac_u
            d_formula = cs.lookup(code, "d", here("l2_code"))
            data["d"][i] = _F(d_formula or "0", cs.values[str(code)]["d"])
            mine = link2[link2["target"] == oid]
            for kind in ("capped", "uncapped"):
                rows = mine[mine["kind"] == kind]
                for c in CASES if kind == "capped" else ("base",):
                    deduct = _weighted(rows, values[c])
                    key = f"deduct_{c}" if kind == "capped" else "deduct_uncapped"
                    data[key][i] = _F(
                        f"SUMIFS({l2t.rng('v_' + c)},{l2t.rng('target_no')},{here('no')},"
                        f'{l2t.rng("kind")},"{kind}")',
                        deduct,
                    )
            for c in CASES:
                data[f"b2_{c}"][i] = _F(
                    f"IF({here('f')}>0,MAX({here('post_move')}-{here('deduct_' + c)},0),0)",
                    float(getattr(row, f"basis_{c}")),
                )
                data[f"l2_{c}"][i] = _F(
                    f"{here('b2_' + c)}*{here('d')}*{here('pi_' + c)}", values[c][oid]
                )
            data["gross_gap"][i] = _F(f"{here('b2_base')}*{here('d')}", float(row.gross_gap))
            data["forgone"][i] = _F(
                f"IF({here('f_uncapped')}>0,MAX({here('post_move_uncapped')}-"
                f"{here('deduct_uncapped')},0),0)*{here('d')}*{here('pi_base')}-{here('l2_base')}",
                _forgone(results, str(code)),
            )
        else:
            for c in CASES:
                data[f"l3_{c}"][i] = _F(
                    f"SUMIFS({pt.rng('cash_' + c)},{pt.rng('opp_no')},{here('no')})",
                    values[c][oid],
                )
            data["gross_gap"][i] = _F(
                f"SUMIFS({pt.rng('gross')},{pt.rng('opp_no')},{here('no')})", float(row.gross_gap)
            )
        if lever != 3:
            data["event_share"][i] = float(engine.event_share.get(oid, 0.0))
            data["spend_moved"][i] = float(engine.spend_moved.get(oid, 0.0))
            for c in CASES:
                data[f"cost_{c}"][i] = _F(
                    f"(Switch_Cost_Fixed*{here('event_share')}+Switch_Cost_Pct*"
                    f"{here('spend_moved')})*{here('pi_' + c)}",
                    float(costs[c][i]),
                )
        data["available_month"][i] = int(row.available_month)
        data["start_month"][i] = int(starts[i])
        data["start_quarter"][i] = int(quarters[i])
        data["start_year"][i] = int((quarters[i] - 1) // 4 + 1)
        data["sites"][i] = row.sites_affected
        data["complexity"][i] = float(row.complexity)
        data["wave"][i] = int(row.wave)
        for q in range(1, QUARTERS + 1):
            value = float(factors[i, q - 1])
            if recurring[i] and engine.method == GLOBAL_RAMP:
                data[f"q{q}"][i] = _F(f"Ramp_Year{(q - 1) // 4 + 1}/4", value)
            else:
                data[f"q{q}"][i] = value
        for y in (1, 2, 3):
            first, last = opp.letter(f"q{4 * y - 3}"), opp.letter(f"q{4 * y}")
            share = float(factors[i, 4 * y - 4 : 4 * y].sum())
            data[f"y{y}"][i] = _F(f"SUM({first}{r}:{last}{r})", share)
    return book.table(sheet, "Opportunities", _OPP_COLS, data)


def _write_links(book: _Book, engine: _Engine, lay: _Layout) -> None:
    """How savings travel down the declining baseline: shares stored as values."""
    sheet = "Links"
    book.furnish(
        sheet,
        "Links between levers",
        "Left: the share of each lever-1 saving that rests on a lever-2 category's base. "
        "Right: the lever-1 and lever-2 savings that fall on each payment-terms vendor group.",
    )
    values = _case_values(book.results.opportunities)
    opp = lay.opp
    link2 = engine.lever2_links
    data2: dict[str, list[Any]] = {c.key: [] for c in _LINK2_COLS}
    for i, row in enumerate(link2.itertuples(index=False)):
        data2["target_no"].append(lay.numbers[row.target])
        data2["target"].append(row.target)
        data2["kind"].append(row.kind)
        data2["source_no"].append(lay.numbers[row.source])
        data2["source"].append(row.source)
        data2["coef"].append(float(row.coef))
        coef, src = lay.links2.here("coef", i), lay.links2.here("source_no", i)
        for c in CASES:
            data2[f"v_{c}"].append(
                _F(
                    f"{coef}*SUMIFS({opp.rng('l1_' + c)},{opp.rng('no')},{src})",
                    float(row.coef) * values[c][row.source],
                )
            )
    book.table(sheet, "Lever2Links", _LINK2_COLS, data2)
    pt = book.results.payment_terms
    link3 = engine.lever3_links
    data3: dict[str, list[Any]] = {c.key: [] for c in _LINK3_COLS}
    for i, row in enumerate(link3.itertuples(index=False)):
        group = int(row.group)
        lever = 1 if str(row.source).startswith("L1:") else 2
        data3["target_no"].append(group + 1)
        data3["target"].append(f"{pt['company'].iloc[group]} | {pt['parent_id'].iloc[group]}")
        data3["source_no"].append(lay.numbers[row.source])
        data3["source"].append(row.source)
        data3["source_lever"].append(lever)
        data3["coef"].append(float(row.coef))
        coef, src = lay.links3.here("coef", i), lay.links3.here("source_no", i)
        for c in CASES:
            data3[f"v_{c}"].append(
                _F(
                    f"{coef}*SUMIFS({opp.rng(f'l{lever}_{c}')},{opp.rng('no')},{src})",
                    float(row.coef) * values[c][row.source],
                )
            )
    book.table(sheet, "Lever3Links", _LINK3_COLS, data3, first_col=_LINK3_FIRST_COL)


def _write_payment_terms(book: _Book, engine: _Engine, lay: _Layout) -> None:
    """Per shared vendor group: terms, retained spend, deductions and cash (PRD 5.4)."""
    sheet = "Payment_Terms"
    book.furnish(
        sheet,
        "Payment terms",
        "One-time cash, never a saving. S = retained spend less the savings already counted on "
        "it; cash = days gained / 365 x S x capture probability.",
    )
    results = book.results
    pt = results.payment_terms.reset_index(drop=True)
    names = parent_labels(results, CLEAN)
    links3, table = lay.links3, lay.pt
    link_frame = engine.lever3_links
    values = _case_values(results.opportunities)
    data: dict[str, list[Any]] = {c.key: [] for c in _PT_COLS}
    for i, row in enumerate(pt.itertuples(index=False)):

        def here(key: str, _i: int = i) -> str:
            return table.here(key, _i)

        gap = float(engine.gap_days[i]) if i < len(engine.gap_days) else 0.0
        data["no"].append(i + 1)
        data["parent_id"].append(row.parent_id)
        data["vendor"].append(names.get(row.parent_id, row.parent_id))
        data["company"].append(row.company)
        data["status"].append(row.status)
        data["basis"].append(row.basis)
        data["reason"].append(row.reason)
        data["T"].append(row.T)
        data["T_star"].append(row.T_star)
        data["gap_days"].append(gap)
        data["spend"].append(float(row.spend))
        data["coverage"].append(row.coverage)
        data["retained"].append(float(engine.retained[i]) if i < len(engine.retained) else 0.0)
        mine = link_frame[link_frame["group"] == i]
        for c in CASES:
            deduct = _weighted(mine, values[c])
            data[f"deduct_{c}"].append(
                _F(
                    f"SUMIFS({links3.rng('v_' + c)},{links3.rng('target_no')},{here('no')})",
                    deduct,
                )
            )
            data[f"s_{c}"].append(
                _F(
                    f"MAX({here('retained')}-{here('deduct_' + c)},0)",
                    float(getattr(row, f"S_{c}")),
                )
            )
            data[f"cash_{c}"].append(
                _F(
                    f"{here('gap_days')}/{DAYS_PER_YEAR:g}*{here('s_' + c)}*Pi3_{_CASE_TITLE[c]}",
                    float(getattr(row, f"cash_{c}")),
                )
            )
        data["gross"].append(
            _F(
                f"{here('gap_days')}/{DAYS_PER_YEAR:g}*{here('s_base')}",
                gap / DAYS_PER_YEAR * float(row.S_base),
            )
        )
        data["opp_no"].append(lay.numbers.get(f"L3:{row.parent_id}", 0))
    book.table(sheet, "PaymentTerms", _PT_COLS, data)


# ---------------------------------------------------------------- clean detail tabs


def _write_bridge_detail(book: _Book) -> _Table:
    sheet = "Bridge_Detail"
    book.furnish(
        sheet,
        "Bridge detail",
        "One row per item, buying group and bridge step: the group's naive gap and the dollars "
        "the step removes. Bridge steps 1-6 are SUMIFS over this table by step.",
    )
    results = book.results
    detail = results.bridge_detail.copy()
    names = parent_labels(results, CLEAN)
    items = item_labels(results)
    detail["vendor"] = detail["parent_id"].map(names)
    detail["description"] = detail["canonical_item_id"].map(items)
    cols = [
        Col("step", "Step", "int", 6),
        Col("step_name", "Step name", width=24),
        Col("canonical_item_id", "Canonical item", width=12),
        Col("description", "Description", width=36),
        Col("item_tier", "Item tier", width=7),
        Col("group_id", "Buying group", width=30),
        Col("company", "Company", width=10),
        Col("site", "Site", width=12),
        Col("parent_id", "Parent id", width=14),
        Col("vendor", "Vendor", width=24),
        Col("naive_gap", "Naive gap", "money"),
        Col("amount_removed", "Amount removed", "money"),
    ]
    return book.table(sheet, "BridgeDetail", cols, _frame_data(detail, cols))


def _write_price_variance(book: _Book) -> _Table:
    sheet = "Price_Variance"
    book.furnish(
        sheet,
        "Price variance",
        "Each buying group's price per base unit against the benchmark. Internal variance "
        "(gaps the benchmark holder's own sites could close without the deal) is listed "
        "separately on the right and is not a synergy.",
    )
    results = book.results
    groups = results.price_groups.copy()
    names = parent_labels(results, CLEAN)
    items = item_labels(results)
    groups["vendor"] = groups["parent_id"].map(names)
    groups["description"] = groups["canonical_item_id"].map(items)
    groups["gap_per_unit"] = (groups["p"] - groups["p_star"]).clip(lower=0.0)
    cols = [
        Col("group_id", "Buying group", width=30),
        Col("canonical_item_id", "Canonical item", width=12),
        Col("description", "Description", width=36),
        Col("l2_code", "L2 code", width=9),
        Col("company", "Company", width=10),
        Col("site", "Site", width=12),
        Col("parent_id", "Parent id", width=14),
        Col("vendor", "Vendor", width=24),
        Col("item_tier", "Item tier", width=7),
        Col("conv_status", "Unit conversion", width=11),
        Col("incoterm", "Incoterm", width=9),
        Col("n_lines", "Lines", "int"),
        Col("q", "Annual base-unit quantity", "num"),
        Col("p", "Unit price p", "price"),
        Col("min_price", "Lowest price (naive)", "price"),
        Col("p_star", "Benchmark price p*", "price"),
        Col("benchmark_company", "Benchmark holder", width=11),
        Col("gap_per_unit", "Gap per unit", "price"),
        Col("a", "Contract-open share a", "share"),
        Col("change_type", "Change type", width=12),
        Col("internal", "Internal variance", width=9),
        Col("incoterm_held", "Held: incoterms", width=9),
        Col("naive_gap", "Naive gap", "money"),
        Col("G1", "Gross gap G1", "money"),
        Col("N1_base", "Net saving (base)", "money"),
        Col("opportunity_id", "Opportunity", width=28),
    ]
    table = book.table(sheet, "PriceVariance", cols, _frame_data(groups, cols))
    internal = results.internal_variance.copy()
    internal["description"] = internal["canonical_item_id"].map(items)
    icols = [
        Col("canonical_item_id", "Item (internal)", width=12),
        Col("description", "Description (internal)", width=30),
        Col("l2_code", "L2 (internal)", width=9),
        Col("tier", "Tier (internal)", width=7),
        Col("benchmark_company", "Benchmark holder (internal)", width=11),
        Col("benchmark_price", "Benchmark price (internal)", "price"),
        Col("internal_variance", "Internal variance", "money"),
        Col("groups", "Groups", "int"),
        Col("sites_affected", "Sites", "int"),
    ]
    book.table(
        sheet,
        "InternalVariance",
        icols,
        _frame_data(internal, icols),
        first_col=len(cols) + 1,
        freeze=False,
    )
    return table


def _cube_frame(results: Results, engine: _Engine) -> pd.DataFrame:
    """Lines summed over identical (company, site, parent, entity, category, item, unit)."""
    lines = results.lines
    parent = (
        lines["parent_id"].astype(object).where(lines["parent_id"].notna(), lines["vendor_key"])
    )
    frame = pd.DataFrame(
        {
            "company": lines["company"].astype(object),
            "site": lines["site"].astype(object).where(lines["site"].notna(), ""),
            "parent_id": parent.astype(str),
            "legal_entity_id": lines["legal_entity_id"].astype(object).fillna(""),
            "l1_code": lines["l1_code"].astype(object).fillna(""),
            "l2_code": lines["l2_code"].astype(object).fillna(""),
            "canonical_item_id": lines["canonical_item_id"].astype(object).fillna(""),
            "base_unit": lines["base_unit"].astype(object).fillna(""),
            "qty_base": lines["qty_base"].astype(float),
            "spend": lines["amount"].astype(float),
        }
    )
    keys = [c for c in frame.columns if c not in ("qty_base", "spend")]
    cube = frame.groupby(keys, sort=True).agg(
        qty_base=("qty_base", lambda s: s.sum(min_count=1)),
        spend=("spend", "sum"),
        lines=("spend", "size"),
    )
    cube = cube.reset_index()
    qty = cube["qty_base"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        cube["price"] = np.where(
            (qty > 0) & (cube["canonical_item_id"] != ""), cube["spend"] / qty, np.nan
        )
    cube["addressable"] = np.where(cube["l2_code"].isin(engine.addressable_l2), "Yes", "No")
    return cube.replace({"": None})


def _write_spend_cube_clean(book: _Book, engine: _Engine) -> _Table:
    sheet = "Spend_Cube"
    book.furnish(
        sheet,
        "Spend cube",
        "Unified in-scope lines, summed over identical company, site, parent vendor, legal "
        "entity, category, canonical item and base unit. Spend sums to the baseline.",
    )
    results = book.results
    cube = _cube_frame(results, engine)
    names = parent_labels(results, CLEAN)
    labels = category_labels(results, CLEAN)
    cube["vendor"] = cube["parent_id"].map(names)
    cube["category"] = [category_label(labels, c) for c in cube["l2_code"]]
    cols = [
        Col("company", "Company", width=10),
        Col("site", "Site", width=12),
        Col("parent_id", "Parent id", width=14),
        Col("vendor", "Parent vendor", width=26),
        Col("legal_entity_id", "Legal entity", width=10),
        Col("l1_code", "L1", width=6),
        Col("l2_code", "L2", width=8),
        Col("category", "Category", width=28),
        Col("canonical_item_id", "Canonical item", width=11),
        Col("base_unit", "Base unit", width=8),
        Col("qty_base", "Base-unit quantity", "num"),
        Col("price", "Price per base unit", "price"),
        Col("spend", "Spend", "money"),
        Col("addressable", "Addressable", width=10),
        Col("lines", "Lines", "int", 7),
    ]
    return book.table(sheet, "SpendCube", cols, _frame_data(cube, cols))


def _write_risk_clean(book: _Book, lay: _Layout) -> None:
    sheet = "Risk"
    book.furnish(
        sheet,
        "Risk guardrails",
        "Vendor shares and concentration index before and after consolidation, the cap, "
        "savings forgone (per category, repeated on each vendor row) and sole-source flags.",
    )
    results = book.results
    risk = results.category_risk.copy()
    risk["vendor"] = risk["parent_id"].map(parent_labels(results, CLEAN))
    labels = category_labels(results, CLEAN)
    risk["category"] = [category_label(labels, c) for c in risk["l2_code"]]
    cols = [
        Col("l2_code", "L2", width=8),
        Col("category", "Category", width=28),
        Col("parent_id", "Parent id", width=14),
        Col("vendor", "Parent vendor", width=26),
        Col("preferred", "Preferred", width=9),
        Col("spend_before", "Spend before", "money"),
        Col("spend_after", "Spend after", "money"),
        Col("share_before", "Share before", "share"),
        Col("share_after", "Share after", "share"),
        Col("criticality", "Criticality", width=11),
        Col("cap", "Cap", "share"),
        Col("lever2_status", "Lever-2 status", width=13),
        Col("hhi_before", "HHI before", "int"),
        Col("hhi_after", "HHI after", "int"),
        Col("parents_before", "Vendors before", "int"),
        Col("parents_after", "Vendors after", "int"),
        Col("sole_source_category", "Sole source after", width=9),
        Col("sole_source_items", "Sole-source items", "int"),
        Col("sole_source_item_ids", "Sole-source item ids", width=30),
        Col("savings_forgone", "Savings forgone (category)", "money"),
    ]
    data = _frame_data(risk, cols)
    opp = lay.opp
    forgone = []
    for code, value in zip(risk["l2_code"], risk["savings_forgone"], strict=True):
        number = lay.numbers.get(f"L2:{code}")
        if number is None:
            forgone.append(float(value))
        else:
            forgone.append(
                _F(f"SUMIFS({opp.rng('forgone')},{opp.rng('no')},{number})", float(value))
            )
    data["savings_forgone"] = forgone
    book.table(sheet, "Risk", cols, data)


def _write_vendor_map(book: _Book) -> None:
    sheet = "Vendor_Map"
    book.furnish(sheet, "Vendor map", "Every source vendor -> legal entity -> parent vendor.")
    results = book.results
    vm = results.vendor_map.copy()
    vm["parent"] = vm["parent_id"].map(parent_labels(results, CLEAN))
    cols = [
        Col("vendor_key", "Vendor key", width=18),
        Col("company", "Company", width=10),
        Col("vendor_id", "Vendor id", width=10),
        Col("vendor_name", "Vendor name", width=30),
        Col("name_normalised", "Normalised name", width=26),
        Col("legal_entity_id", "Legal entity", width=10),
        Col("parent_id", "Parent id", width=14),
        Col("parent", "Parent vendor", width=26),
        Col("stage", "Stage", width=7),
        Col("score", "Score", "num"),
        Col("tier", "Tier", width=6),
        Col("spend", "Spend", "money"),
        Col("evidence", "Evidence", width=50),
    ]
    book.table(sheet, "VendorMap", cols, _frame_data(vm, cols))


def _write_item_map(book: _Book) -> None:
    sheet = "Item_Map"
    book.furnish(sheet, "Item map", "Every source item -> canonical item, with its attributes.")
    cols = [
        Col("item_record_id", "Item record", width=22),
        Col("company", "Company", width=10),
        Col("item_key", "Item key", width=16),
        Col("canonical_item_id", "Canonical item", width=11),
        Col("partner_id", "Matched record", width=22),
        Col("description", "Description", width=36),
        Col("l2_code", "L2", width=8),
        Col("stage", "Stage", width=7),
        Col("score", "Score", "num"),
        Col("tier", "Tier", width=6),
        Col("attributes", "Attributes", width=36),
        Col("spend", "Spend", "money"),
    ]
    frame = book.results.item_map
    book.table(sheet, "ItemMap", cols, _frame_data(frame, cols))


def _write_review_log(book: _Book) -> None:
    sheet = "Review_Log"
    book.furnish(sheet, "Review log", "Human decisions with timestamps and notes.")
    cols = [
        Col("pair_id", "Pair", width=40),
        Col("type", "Type", width=14),
        Col("decision", "Decision", width=10),
        Col("pack_qty", "Pack quantity", "num"),
        Col("note", "Note", width=40),
        Col("decided_at", "Decided at", width=22),
    ]
    book.table(sheet, "ReviewLog", cols, _frame_data(book.results.review_log, cols))


# ---------------------------------------------------------------- shared tabs


def _write_scorecard(book: _Book) -> None:
    sheet = "Scorecard"
    book.furnish(
        sheet, "Accuracy scorecard", "Held-out accuracy of the tool against a naive baseline."
    )
    card = scorecard_table(book.results, book.mode)
    if isinstance(card, Unavailable):
        ws = book.sheets[sheet]
        message = card.message or "The scorecard is available for the demo data only."
        ws.write_string(_HEADER_ROW, 0, message, book.fmt())
        return
    cols = [
        Col("label", "Metric", width=26),
        Col("tool", "Tool (held out)", "num"),
        Col("baseline", "Baseline (held out)", "num"),
        Col("tool_tuning_mean", "Tool (tuning mean)", "num"),
        Col("baseline_tuning_mean", "Baseline (tuning mean)", "num"),
        Col("target", "Target", width=12),
        Col("passed", "Passed", width=8),
    ]
    book.table(sheet, "Scorecard", cols, _frame_data(card, cols))


def _write_data_quality(book: _Book) -> None:
    sheet = "Data_Quality"
    book.furnish(sheet, "Data quality", "Validation findings with row counts and dollar values.")
    findings = data_quality_summary(book.results, book.mode)["findings"]
    cols = [
        Col("severity", "Severity", width=10),
        Col("company", "Company", width=10),
        Col("rule", "Rule", width=22),
        Col("rows", "Rows", "int"),
        Col("amount", "Amount", "money"),
        Col("message", "What happened", width=70),
        Col("fix", "What to do", width=40),
    ]
    book.table(sheet, "DataQuality", cols, _frame_data(findings, cols))


def _phasing_costs(results: Results) -> pd.DataFrame:
    phasing = results.phasing
    costs = phasing[phasing["row_type"] == "cost"].groupby("year")[list(CASES)].sum()
    return costs.reindex([1, 2, 3], fill_value=0.0)


_YEAR_COLS: tuple[Col, ...] = (
    Col("year", "Year", width=8),
    *[Col(f"wave_{w}", f"Wave {w} savings (base)", "money") for w in (1, 2, 3)],
    *_case_cols("savings", "Realised savings {case}"),
    *_case_cols("cost", "One-time cost {case}"),
    *_case_cols("net", "Net value {case}"),
)
_QUARTER_COLS: tuple[Col, ...] = (
    Col("quarter", "Quarter", "int", 8),
    Col("year", "Year", "int", 6),
    *[Col(f"wave_{w}", f"Wave {w} savings (base)", "money") for w in (1, 2, 3)],
    Col("savings", "Realised savings (base)", "money"),
    Col("cost", "One-time cost (base)", "money"),
    Col("cash", "Cash release (base, one-time)", "money"),
)


def _write_phasing(book: _Book, opp: _Table | None) -> _Table:
    """Realised savings by year and quarter, costs and net value; formulas when ``opp`` is set.

    Costs are negative. Cash release has its own column and is never added to savings.
    """
    sheet = "Phasing"
    book.furnish(
        sheet,
        "Phasing",
        "Realised savings by year and wave, one-time costs (negative) and net three-year value; "
        "below, by quarter. Cash release is one-time and is never added to savings.",
    )
    results = book.results
    by_year = phasing_by_year(results, book.mode)
    by_quarter = phasing_by_quarter(results, book.mode)
    costs = _phasing_costs(results)
    year_table = _Table(sheet, _HEADER_ROW, 0, tuple(c.key for c in _YEAR_COLS), 4)
    data: dict[str, list[Any]] = {c.key: [] for c in _YEAR_COLS}
    live = opp is not None
    for i in range(4):
        total = i == 3
        year = i + 1
        data["year"].append("Total" if total else f"Year {year}")
        record = by_year.iloc[i]
        cached = {
            **{f"wave_{w}": float(record[f"wave_{w}"]) for w in (1, 2, 3)},
            "savings_low": float(record["savings_low"]),
            "savings_base": float(record["savings"]),
            "savings_high": float(record["savings_high"]),
            **{f"cost_{c}": -float(costs[c].sum() if total else costs[c].iloc[i]) for c in CASES},
            **{f"net_{c}": float(record[f"net_{c}"]) for c in CASES},
        }
        for key, value in cached.items():
            if not live:
                data[key].append(value)
                continue
            if total:
                letter = year_table.letter(key)
                formula = f"SUM({letter}{year_table.row(0)}:{letter}{year_table.row(2)})"
            elif key.startswith("wave_"):
                formula = (
                    f"SUMPRODUCT(({opp.rng('wave')}={key[-1]})*({opp.rng('l1_base')}+"
                    f"{opp.rng('l2_base')})*{opp.rng(f'y{year}')})"
                )
            elif key.startswith("savings_"):
                c = key.split("_")[1]
                formula = (
                    f"SUMPRODUCT({opp.rng('l1_' + c)},{opp.rng(f'y{year}')})+"
                    f"SUMPRODUCT({opp.rng('l2_' + c)},{opp.rng(f'y{year}')})"
                )
            elif key.startswith("cost_"):
                c = key.split("_")[1]
                formula = f"-SUMIFS({opp.rng('cost_' + c)},{opp.rng('start_year')},{year})"
            else:
                c = key.split("_")[1]
                formula = f"{year_table.here('savings_' + c, i)}+{year_table.here('cost_' + c, i)}"
            data[key].append(_F(formula, value))
    book.table(sheet, "PhasingYear", _YEAR_COLS, data)
    quarter_header = _HEADER_ROW + 7
    quarter_table = _Table(sheet, quarter_header, 0, tuple(c.key for c in _QUARTER_COLS), 12)
    qdata: dict[str, list[Any]] = {c.key: [] for c in _QUARTER_COLS}
    for i, record in enumerate(by_quarter.itertuples(index=False)):
        q = int(record.quarter)
        qdata["quarter"].append(q)
        qdata["year"].append(int(record.year))
        cached = {
            **{f"wave_{w}": float(getattr(record, f"wave_{w}")) for w in (1, 2, 3)},
            "savings": float(record.savings),
            "cost": float(record.cost),
            "cash": float(record.cash),
        }
        for key, value in cached.items():
            if not live:
                qdata[key].append(value)
                continue
            if key.startswith("wave_"):
                formula = (
                    f"SUMPRODUCT(({opp.rng('wave')}={key[-1]})*({opp.rng('l1_base')}+"
                    f"{opp.rng('l2_base')})*{opp.rng(f'q{q}')})"
                )
            elif key == "savings":
                first, last = quarter_table.letter("wave_1"), quarter_table.letter("wave_3")
                formula = f"SUM({first}{quarter_table.row(i)}:{last}{quarter_table.row(i)})"
            elif key == "cost":
                formula = f"-SUMIFS({opp.rng('cost_base')},{opp.rng('start_quarter')},{q})"
            else:
                formula = f"SUMIFS({opp.rng('l3_base')},{opp.rng('start_quarter')},{q})"
            qdata[key].append(_F(formula, value))
    book.table(
        sheet, "PhasingQuarter", _QUARTER_COLS, qdata, header_row=quarter_header, freeze=False
    )
    return year_table


# ---------------------------------------------------------------- bridge and summary


def _write_bridge(
    book: _Book, naive_formula: str, raw_formula: Callable[[int], str], note: str
) -> None:
    """Naive figure, seven removal steps (negatives carried forward), lever 1, lever 2.

    Step 7 is the gross after step 6 less the lever-1 base saving, so the bridge
    always ties: naive - sum of steps = lever 1 (PRD 5.2, 7.1).
    """
    sheet = "Bridge"
    ws = book.furnish(sheet, "Naive-to-defensible bridge", note)
    totals = book.results.totals
    lever1 = totals["lever1"]
    heads = (
        "Step",
        "Bar",
        "Raw step (from detail)",
        "Negative carried forward",
        "Amount",
        "Low",
        "High",
        "Exported by the tool",
    )
    for j, head in enumerate(heads):
        ws.write_string(_HEADER_ROW, j, head, book.fmt("text", "head"))
    ws.set_column(0, 0, 6)
    ws.set_column(1, 1, 46)
    ws.set_column(2, 7, 16)
    money, formula = book.fmt("money", "formula"), book.fmt("money", "fixed")
    first = _HEADER_ROW + 1
    ws.write_number(first, 0, 0, book.fmt("int"))
    ws.write_string(first, 1, "Naive figure", book.fmt())
    ws.write_formula(first, 4, naive_formula, money, float(lever1["naive"]))
    ws.write_number(first, 7, float(lever1["naive"]), formula)
    book.define("Bridge_Naive", sheet, first, 4)
    carry = 0.0
    for i, name in enumerate(STEP_NAMES, start=1):
        r = first + i
        raw = float(lever1["bridge_raw"][f"step_{i}"])
        shown = float(lever1["bridge"][f"step_{i}"])
        ws.write_number(r, 0, i, book.fmt("int"))
        ws.write_string(r, 1, name, book.fmt())
        ws.write_formula(r, 2, raw_formula(i), money, raw)
        previous = f"D{r}" if i > 1 else "0"
        if i < len(STEP_NAMES):
            out = raw + carry if raw + carry < 0 else 0.0
            ws.write_formula(r, 3, f"IF(C{r + 1}+{previous}<0,C{r + 1}+{previous},0)", money, out)
            ws.write_formula(r, 4, f"C{r + 1}+{previous}-D{r + 1}", money, shown)
            carry = out
        else:
            steps = f"E{first + 2}:E{first + len(STEP_NAMES)}"
            ws.write_formula(r, 4, f"Bridge_Naive-SUM({steps})-Lever1_Base", money, shown)
        ws.write_number(r, 7, shown, formula)
        book.define(f"Bridge_Step{i}", sheet, r, 4)
    levers = totals["levers"]
    recurring = totals["recurring"]
    tail = [
        ("Defensible price harmonisation (lever 1)", "Lever1_Base", levers["lever1"]["base"]),
        ("+ Volume consolidation (lever 2)", "Lever2_Base", levers["lever2"]["base"]),
        ("Defensible run-rate saving", "Recurring_Base", recurring["base"]),
    ]
    for k, (label, name, value) in enumerate(tail):
        r = first + len(STEP_NAMES) + 1 + k
        ws.write_string(r, 1, label, book.fmt("text", "label"))
        ws.write_formula(r, 4, name, money, float(value))
        ws.write_number(r, 7, float(value), formula)
    last = first + len(STEP_NAMES) + 3
    ws.write_formula(last, 5, "Recurring_Low", money, float(recurring["low"]))
    ws.write_formula(last, 6, "Recurring_High", money, float(recurring["high"]))
    residual = last + 2
    ws.write_string(residual, 1, "Tie-out: naive - steps - lever 1 (should be 0)", book.fmt())
    steps = f"E{first + 2}:E{first + 1 + len(STEP_NAMES)}"
    ws.write_formula(
        residual,
        4,
        f"Bridge_Naive-SUM({steps})-E{first + len(STEP_NAMES) + 2}",
        money,
        float(totals["checks"]["bridge_tie_out_difference"]),
    )
    book.define("Bridge_Residual", sheet, residual, 4)
    ws.freeze_panes(_HEADER_ROW + 1, 0)


@dataclass(frozen=True)
class _Line:
    key: str
    label: str
    cases: tuple[str, ...]
    kind: str = "money"


_SECTIONS: tuple[tuple[str, tuple[_Line, ...]], ...] = (
    (
        "Run-rate P&L saving (recurring)",
        (
            _Line("Recurring", "Defensible run-rate saving (lever 1 + lever 2)", CASES),
            _Line("Lever1", "Price harmonisation (lever 1)", CASES),
            _Line("Lever2", "Volume consolidation (lever 2)", CASES),
            _Line("Naive", "Naive price-gap figure (shown for contrast only)", ("base",)),
            _Line("TierA", "Lever 1 resting on tier A matches", ("base",)),
            _Line("TierB", "Lever 1 resting on tier B matches", ("base",)),
            _Line("Pending_Upside", "Upside pending review (not counted)", ("base",)),
            _Line("Savings_Forgone", "Savings forgone to protect supply resilience", ("base",)),
        ),
    ),
    (
        "One-time (never added to the run-rate)",
        (
            _Line("Cash", "One-time cash release (lever 3)", CASES),
            _Line("Financing", "Annual financing value of the cash (memo; not EBITDA)", CASES),
            _Line("OneTime_Cost", "One-time cost", CASES),
        ),
    ),
    (
        "Phasing",
        (
            _Line("Realised_Y1", "Realised savings, year 1", CASES),
            _Line("Realised_Y2", "Realised savings, year 2", CASES),
            _Line("Realised_Y3", "Realised savings, year 3", CASES),
            _Line("Window_Cost", "One-time costs in years 1-3", CASES),
            _Line("Net3Y", "Net three-year value", CASES),
        ),
    ),
    (
        "Spend and reconciliation",
        (
            _Line("Baseline", "In-scope spend (baseline)", ("base",)),
            _Line("Addressable", "Addressable spend (categories both companies buy)", ("base",)),
            _Line("Net_Run_Rate", "Net run-rate spend", CASES),
            _Line("Share_Total", "Base case as a share of total spend", ("base",), "share"),
            _Line(
                "Share_Addressable", "Base case as a share of addressable spend", ("base",), "share"
            ),
        ),
    ),
)


def _name(key: str, case: str, cases: tuple[str, ...]) -> str:
    return key if cases == ("base",) else f"{key}_{_CASE_TITLE[case]}"


#: Summary figure -> defined name per case (``base`` only for single figures).
SUMMARY_NAMES: dict[str, dict[str, str]] = {
    line.key: {case: _name(line.key, case, line.cases) for case in line.cases}
    for _, lines in _SECTIONS
    for line in lines
}


def _exported(totals: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    """The engine's figures, keyed like :data:`SUMMARY_NAMES`."""
    realised = totals["phasing"]["realised"]
    net3 = totals["phasing"]["net_three_year"]
    out: dict[str, dict[str, float]] = {
        "Recurring": dict(totals["recurring"]),
        "Lever1": {c: totals["levers"]["lever1"][c] for c in CASES},
        "Lever2": {c: totals["levers"]["lever2"][c] for c in CASES},
        "Naive": {"base": totals["lever1"]["naive"]},
        "TierA": {"base": totals["lever1"]["tier_a"]["base"]},
        "TierB": {"base": totals["lever1"]["tier_b"]["base"]},
        "Pending_Upside": {"base": totals["lever1"]["upside_pending_review"]},
        "Savings_Forgone": {"base": totals["lever2"]["savings_forgone"]},
        "Cash": dict(totals["one_time"]["cash"]),
        "Financing": dict(totals["memo"]["financing_value"]),
        "OneTime_Cost": dict(totals["one_time"]["costs"]),
        **{f"Realised_Y{y}": dict(realised[f"year{y}"]) for y in (1, 2, 3)},
        "Window_Cost": {
            c: net3[c] - sum(realised[f"year{y}"][c] for y in (1, 2, 3)) for c in CASES
        },
        "Net3Y": dict(net3),
        "Baseline": {"base": totals["spend"]["baseline"]},
        "Addressable": {"base": totals["spend"]["addressable"]},
        "Net_Run_Rate": dict(totals["spend"]["net_run_rate"]),
        "Share_Total": {"base": totals["reconciliation"]["total_spend"]["share"]},
        "Share_Addressable": {"base": totals["reconciliation"]["addressable_spend"]["share"]},
    }
    return {k: {c: float(v) for c, v in cases.items()} for k, cases in out.items()}


def _write_summary(
    book: _Book,
    sources: Mapping[str, Callable[[str], str]],
    checks: Sequence[tuple[str, str]],
) -> None:
    """Headline range, levers, cash, cost, phasing and spend; every figure a formula.

    ``sources[key](case)`` is the formula for a figure that reads the detail tabs;
    the rest are arithmetic on other Summary names. ``checks`` are ``(label,
    difference formula)`` pairs: internal identities between Summary and the
    detail tabs, each 0 when they tie. The check cell sums them, so it stays OK
    after any assumption edit. The exported values sit beside the live figures
    for reference only.
    """
    sheet = "Summary"
    results = book.results
    ws = book.furnish(
        sheet,
        "Summary",
        "Every figure is a formula over the detail tabs and the named assumptions. Recurring "
        "savings and one-time amounts are never added together.",
    )
    ws.write_string(
        3, 0, headline(results, book.mode)["text"] + " (as exported)", book.fmt("text", "label")
    )
    heads = (
        "Figure",
        "Low",
        "Base",
        "High",
        "",
        "As exported low",
        "As exported base",
        "As exported high",
        "Change since export (base)",
    )
    for j, head in enumerate(heads):
        if head:
            ws.write_string(_HEADER_ROW + 1, j, head, book.fmt("text", "head"))
    ws.set_column(0, 0, 54)
    ws.set_column(1, 3, 16)
    ws.set_column(4, 4, 2)
    ws.set_column(5, 8, 15)
    exported = _exported(results.totals)
    arithmetic: dict[str, Callable[[str], str]] = {
        "Recurring": lambda c: f"Lever1_{_CASE_TITLE[c]}+Lever2_{_CASE_TITLE[c]}",
        "Financing": lambda c: f"Cash_{_CASE_TITLE[c]}*Cost_Of_Capital",
        "Net_Run_Rate": lambda c: f"Baseline-Recurring_{_CASE_TITLE[c]}",
        "Share_Total": lambda c: "IF(Baseline>0,Recurring_Base/Baseline,0)",
        "Share_Addressable": lambda c: "IF(Addressable>0,Recurring_Base/Addressable,0)",
    }
    row = _HEADER_ROW + 2
    case_col = {"low": 1, "base": 2, "high": 3}
    for section, lines in _SECTIONS:
        ws.write_string(row, 0, section, book.fmt("text", "section"))
        row += 1
        for line in lines:
            ws.write_string(row, 0, line.label, book.fmt())
            for case in line.cases:
                col = case_col[case]
                build = sources.get(line.key) or arithmetic[line.key]
                value = exported[line.key][case]
                ws.write_formula(row, col, build(case), book.fmt(line.kind, "formula"), value)
                ws.write_number(row, col + 4, value, book.fmt(line.kind, "fixed"))
                book.define(_name(line.key, case, line.cases), sheet, row, col)
            change = f"C{row + 1}-G{row + 1}"
            ws.write_formula(row, 8, change, book.fmt(line.kind, "formula"), 0.0)
            row += 1
        row += 1
    ws.write_string(row, 0, "Within the reference band (total spend)?", book.fmt())
    rec = results.totals["reconciliation"]
    ws.write_formula(
        row,
        2,
        'IF(AND(Share_Total>=Band_Total_Low,Share_Total<=Band_Total_High),"Within","Outside")',
        book.fmt(),
        "Within" if rec["total_spend"]["within"] else "Outside",
    )
    row += 1
    ws.write_string(row, 0, "Within the reference band (addressable spend)?", book.fmt())
    ws.write_formula(
        row,
        2,
        "IF(AND(Share_Addressable>=Band_Addressable_Low,Share_Addressable<="
        'Band_Addressable_High),"Within","Outside")',
        book.fmt(),
        "Within" if rec["addressable_spend"]["within"] else "Outside",
    )
    row += 2
    ws.write_string(row, 0, "Consistency checks (each should be 0)", book.fmt("text", "section"))
    row += 1
    first = row
    for label, formula in checks:
        ws.write_string(row, 0, label, book.fmt())
        ws.write_formula(row, 2, formula, book.fmt("money", "formula"), 0.0)
        row += 1
    ws.write_string(
        row, 0, "Check: Summary totals tie to the detail tabs", book.fmt("text", "label")
    )
    diff = f"SUM(C{first + 1}:C{row})"
    ws.write_formula(row, 2, f'IF(ABS({diff})<0.5,"OK",{diff})', book.fmt("money", "check"), "OK")
    book.define(CHECK_NAME, sheet, row, 2)
    ws.write_string(
        row + 1,
        0,
        "The check is internal: it stays OK when you change an assumption. The As exported "
        "columns show the tool's figures for comparison.",
        book.fmt("text", "note"),
    )
    ws.freeze_panes(_HEADER_ROW + 2, 1)


def _write_readme(book: _Book, engine: _Engine, sheets: Sequence[str]) -> None:
    sheet = "README"
    results = book.results
    ws = book.furnish(sheet, "Tie-Out: procurement synergy workbook")
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 110)
    meta, totals = results.meta, results.totals
    period = meta.get("period") or {}
    spend = (meta.get("in_scope_spend") or {}).get("total", totals["spend"]["baseline"])
    row = _HEADER_ROW

    def line(label: str, text: str, role: str = "data") -> None:
        nonlocal row
        ws.write_string(row, 0, label, book.fmt("text", "label"))
        ws.write_string(row, 1, text, book.fmt("text", role))
        row += 1

    def section(title: str) -> None:
        nonlocal row
        row += 1
        ws.write_string(row, 0, title, book.fmt("text", "section"))
        row += 1

    section("Scope")
    line("Companies", "Acquirer and target, trailing-12-month in-scope spend of both")
    line("Data window", f"{period.get('start', '?')} to {period.get('end', '?')}")
    line("Report date", str(meta.get("report_date") or ""))
    currency = str(totals.get("currency", meta.get("reporting_currency", "USD")))
    line("Reporting currency", currency)
    line("In-scope spend", f"{float(spend):,.0f} {currency}")
    view = "Integration-office view (masked)" if book.mode == MASKED else "Clean-team view"
    line("View mode", view)
    line("Phasing", engine.method.replace("_", " "))
    section("How to read this file")
    for label, text in (
        ("Colours", "Blue font: inputs you may change. Black: formulas. Grey: fixed or exported."),
        ("Summary", "Every figure is a formula over the detail tabs and the named assumptions."),
        ("Check cell", "Summary shows OK when the workbook ties to the tool's results."),
        ("Recurring vs one-time", "Run-rate savings and one-time cash are never added together."),
        (
            "Assumptions",
            "Capture probabilities, discounts, ramp, cost of capital and switching costs "
            "recalculate the workbook. Thresholds, caps, close date and horizon need a re-run.",
        ),
        ("Detail tabs", "Excel tables with frozen headers and filters."),
        ("Negative numbers", "Shown in brackets, following finance convention."),
    ):
        line(label, text)
    if book.mode == MASKED:
        line(
            "Masked workbook",
            "Detail tabs hold aggregated values; Summary and Bridge sum them. Use the "
            "clean-team workbook to test assumptions.",
        )
    section("Data caveats")
    if book.illustrative:
        line("Data", theme.ILLUSTRATIVE_LABEL)
    if not totals["checks"].get("contract_lock_in_assessed", True):
        line("Contract lock-in", "Not assessed: no contract end dates were supplied.")
    if not totals["checks"].get("lever3_enabled", True):
        line("Payment terms", str(totals["checks"].get("lever3_message") or ""))
    for key, text in (meta.get("switched_off") or {}).items():
        line(str(key).replace("_", " ").capitalize(), str(text))
    line(
        "Probabilities",
        "Default capture probabilities and bands are illustrative assumptions, not benchmarks.",
    )
    section("What this analysis cannot see")
    for text in CANNOT_SEE:
        line("", text)
    section("Tabs")
    for name in sheets:
        line(name, _TAB_NOTES.get(name, ""))


_TAB_NOTES = {
    "README": "This page.",
    "Summary": "Headline range, levers, cash, one-time cost, phasing, check cell.",
    "Assumptions": "Every adjustable input in a named cell.",
    "Bridge": "Naive-to-defensible steps as formulas over the detail.",
    "Bridge_Detail": "One row per item, buying group and bridge step.",
    "Bridge_By_Category": "Bridge step amounts per category.",
    "Category_Settings": "Per-category cap, discount and capture probabilities.",
    "Opportunities": "One row per opportunity with gap, probabilities, low/base/high, wave.",
    "Links": "How lever-1 savings travel into the lever-2 and lever-3 bases.",
    "Spend_Cube": "Unified spend by company, site, vendor, category and item.",
    "Price_Variance": "Per matched item and buying group: price, benchmark, gap.",
    "Payment_Terms": "Per shared vendor group: current and target days, spend, cash.",
    "Risk": "Vendor shares, concentration index, cap, savings forgone, sole source.",
    "Phasing": "Realised savings by year and quarter, costs, net three-year value.",
    "Vendor_Map": "Source vendor -> legal entity -> parent.",
    "Item_Map": "Source item -> canonical item.",
    "Review_Log": "Human review decisions.",
    "Scorecard": "Accuracy metrics against the baseline (demo data).",
    "Data_Quality": "Validation findings with rows and dollars.",
}


# ---------------------------------------------------------------- clean workbook


def _build_clean(book: _Book, engine: _Engine) -> None:
    book.add_sheets(CLEAN_SHEETS)
    results = book.results
    lay = _layout(results, engine)
    _write_assumptions(book, engine, live=True)
    cs = _write_category_settings(book, engine)
    opp = _write_opportunities(book, engine, cs, lay)
    _write_links(book, engine, lay)
    _write_payment_terms(book, engine, lay)
    detail = _write_bridge_detail(book)
    groups = _write_price_variance(book)
    cube = _write_spend_cube_clean(book, engine)
    _write_risk_clean(book, lay)
    year = _write_phasing(book, opp)
    _write_vendor_map(book)
    _write_item_map(book)
    _write_review_log(book)
    _write_scorecard(book)
    _write_data_quality(book)
    _write_bridge(
        book,
        f"SUM({groups.rng('naive_gap')})",
        lambda i: f"SUMIFS({detail.rng('amount_removed')},{detail.rng('step')},{i})",
        "Steps 1-6 are SUMIFS over Bridge_Detail by step; step 7 is the gross after step 6 "
        "less the lever-1 base saving on Opportunities.",
    )
    _write_summary(book, _sources(opp, cube, year, tier="clean"), _clean_checks(opp, lay, detail))
    _write_readme(book, engine, CLEAN_SHEETS)


#: Bridge cells holding raw steps 1-6 (column C).
_BRIDGE_RAW = f"Bridge!$C${_HEADER_ROW + 3}:$C${_HEADER_ROW + 1 + len(STEP_NAMES)}"


def _clean_checks(opp: _Table, lay: _Layout, detail: _Table) -> list[tuple[str, str]]:
    """Identities that hold whatever the assumptions: Summary against the detail tabs."""
    pt = lay.pt

    def per_case(build: Callable[[str], str]) -> str:
        return "+".join(f"ABS({build(c)})" for c in CASES)

    return [
        (
            "Lever 1 on Summary less gross gap x probability over in-range rows",
            per_case(
                lambda c: (
                    f"Lever1_{_CASE_TITLE[c]}-SUMPRODUCT(({opp.rng('lever')}=1)*"
                    f'({opp.rng("status")}="in_range")*{opp.rng("gross_gap")}*{opp.rng("pi_" + c)})'
                )
            ),
        ),
        (
            "Lever 2 on Summary less B2 x d x probability over Opportunities",
            per_case(
                lambda c: (
                    f"Lever2_{_CASE_TITLE[c]}-SUMPRODUCT({opp.rng('b2_' + c)},"
                    f"{opp.rng('d')},{opp.rng('pi_' + c)})"
                )
            ),
        ),
        (
            "Cash release on Summary less the Payment_Terms total",
            per_case(lambda c: f"Cash_{_CASE_TITLE[c]}-SUM({pt.rng('cash_' + c)})"),
        ),
        (
            "Bridge raw steps 1-6 less Bridge_Detail",
            f"ABS(SUM({_BRIDGE_RAW})-SUMPRODUCT(({detail.rng('step')}<=6)*"
            f"{detail.rng('amount_removed')}))",
        ),
        ("Naive less the seven bridge steps less lever 1", "ABS(Bridge_Residual)"),
    ]


def _masked_checks(by_category: _Table) -> list[tuple[str, str]]:
    """The masked tabs' identities: the aggregated bridge ties to lever 1 on Opportunities."""
    steps = "+".join(f"SUM({by_category.rng(f'step_{i}')})" for i in range(1, 8))
    return [
        (
            "Bridge_By_Category: naive less all raw steps less lever 1 on Opportunities",
            f"ABS(SUM({by_category.rng('naive')})-({steps})-Lever1_Base)",
        ),
        ("Naive less the seven bridge steps less lever 1", "ABS(Bridge_Residual)"),
    ]


def _sources(
    opp: _Table, cube: _Table, year: _Table, tier: str, forgone: str | None = None
) -> dict[str, Callable[[str], str]]:
    """Summary formulas that read the detail tabs (the same columns in both workbooks)."""

    def year_cell(prefix: str, row: int) -> Callable[[str], str]:
        return lambda c: year.at(f"{prefix}_{c}", row)

    sources: dict[str, Callable[[str], str]] = {
        "Lever1": lambda c: f"SUM({opp.rng('l1_' + c)})",
        "Lever2": lambda c: f"SUM({opp.rng('l2_' + c)})",
        "Cash": lambda c: f"SUM({opp.rng('l3_' + c)})",
        "OneTime_Cost": lambda c: f"SUM({opp.rng('cost_' + c)})",
        "Naive": lambda c: "Bridge_Naive",
        "Pending_Upside": lambda c: f"SUM({opp.rng('upside')})",
        "Baseline": lambda c: f"SUM({cube.rng('spend')})",
        "Addressable": lambda c: f'SUMIFS({cube.rng("spend")},{cube.rng("addressable")},"Yes")',
        **{f"Realised_Y{y}": year_cell("savings", y - 1) for y in (1, 2, 3)},
        "Window_Cost": year_cell("cost", 3),
        "Net3Y": year_cell("net", 3),
    }
    if tier == "clean":
        sources["TierA"] = lambda c: f'SUMIFS({opp.rng("l1_base")},{opp.rng("tier")},"A")'
        sources["TierB"] = lambda c: f'SUMIFS({opp.rng("l1_base")},{opp.rng("tier")},"B")'
        sources["Savings_Forgone"] = lambda c: f"SUM({opp.rng('forgone')})"
    else:
        sources["TierA"] = lambda c: f"SUM({opp.rng('tier_a')})"
        sources["TierB"] = lambda c: f"SUM({opp.rng('tier_b')})"
        sources["Savings_Forgone"] = lambda c: f"SUM({forgone})"
    return sources


# ---------------------------------------------------------------- masked workbook


def _shared(values: pd.Series) -> Any:
    """The value all rows share, else blank (merged "Other" categories)."""
    unique = values.dropna().unique()
    return unique[0] if len(unique) == 1 else None


def _write_category_settings_masked(book: _Book, engine: _Engine) -> None:
    sheet = "Category_Settings"
    book.furnish(
        sheet,
        "Category settings",
        "Effective values per category; categories with fewer than three parent vendors are "
        'merged into "Other" (blank where their values differ).',
    )
    params = engine.params
    labels = category_labels(book.results, MASKED)
    values = _effective_settings(engine)
    frame = pd.DataFrame(
        [
            {
                "category": category_label(labels, code),
                "criticality": str(params.criticality[i]),
                **values[code],
            }
            for i, code in enumerate(params.l2_codes)
        ]
    )
    columns = ["criticality", "cap", "d", *_PI_COLUMNS]
    if frame.empty:
        merged = pd.DataFrame(columns=["category", *columns])
    else:
        merged = frame.groupby("category", sort=True)[columns].agg(_shared).reset_index()
    cols = [
        Col("category", "Category", width=34),
        Col("criticality", "Criticality", width=12),
        Col("cap", "Concentration cap", "share"),
        Col("d", "Volume discount d", "share"),
        *[Col(f"pi2_{c}", f"Lever 2 capture {c}", "share") for c in CASES],
        *[Col(f"pi1_same_{c}", f"Lever 1 same vendor {c}", "share") for c in CASES],
        *[Col(f"pi1_switch_{c}", f"Lever 1 switch {c}", "share") for c in CASES],
    ]
    book.table(sheet, "CategorySettings", cols, _frame_data(merged, cols))


def _masked_opportunities(book: _Book, engine: _Engine) -> pd.DataFrame:
    """Opportunities summed to lever x category (lever 3: one row), as the views label them."""
    results = book.results
    opps = results.opportunities.reset_index(drop=True)
    pi = _opportunity_pi(opps, engine, _effective_settings(engine))
    costs = _opportunity_costs(opps, engine, pi)
    lever = opps["lever"].to_numpy()
    frame = pd.DataFrame(
        {
            "label": opportunity_labels(results, opps, MASKED) if len(opps) else [],
            "lever": lever,
            "count": 1,
            "gross_gap": opps["gross_gap"].astype(float),
            **{f"l{k}_{c}": np.where(lever == k, opps[c], 0.0) for k in (1, 2, 3) for c in CASES},
            "upside": opps["upside_base"].astype(float).fillna(0.0),
            "tier_a": np.where((lever == 1) & (opps["tier"] == "A"), opps["base"], 0.0),
            "tier_b": np.where((lever == 1) & (opps["tier"] == "B"), opps["base"], 0.0),
            **{f"cost_{c}": costs[c] for c in CASES},
            "weighted": opps["complexity"].astype(float) * opps["base"].astype(float),
            "complexity": opps["complexity"].astype(float),
            "base": opps["base"].astype(float),
            "wave": opps["wave"].astype(int),
        }
    )
    sums = [c for c in frame.columns if c not in ("label", "lever", "complexity", "wave")]
    grouped = frame.groupby(["lever", "label"], sort=True)
    out = grouped[sums].sum()
    mean = grouped["complexity"].mean()
    out["complexity"] = np.where(
        out["base"] > 0, out["weighted"] / out["base"].where(out["base"] > 0, 1.0), mean
    )
    waves = frame.groupby(["lever", "label", "wave"])["base"].sum().reset_index()
    top = waves.sort_values(
        ["lever", "label", "base", "wave"], ascending=[True, True, False, True], kind="mergesort"
    ).drop_duplicates(["lever", "label"])
    out = out.reset_index().merge(top[["lever", "label", "wave"]], on=["lever", "label"])
    return out


_MASKED_OPP_COLS: tuple[Col, ...] = (
    Col("lever", "Lever", "int", 6),
    Col("label", "Opportunity", width=44),
    Col("count", "Opportunities", "int"),
    Col("gross_gap", "Gross gap", "money"),
    *_case_cols("l1", "Price saving {case} (lever 1)"),
    *_case_cols("l2", "Volume saving {case} (lever 2)"),
    *_case_cols("l3", "Cash release {case} (lever 3, one-time)"),
    Col("upside", "Upside pending review (base)", "money"),
    Col("tier_a", "Lever 1 on tier A (base)", "money"),
    Col("tier_b", "Lever 1 on tier B (base)", "money"),
    *_case_cols("cost", "One-time cost {case}"),
    Col("complexity", "Complexity (saving-weighted)", "num"),
    Col("wave", "Wave (most saving)", "int"),
)


def _write_bridge_by_category(book: _Book) -> _Table:
    sheet = "Bridge_By_Category"
    book.furnish(
        sheet,
        "Bridge by category",
        "The naive figure and each bridge step's dollars per category (before negative steps "
        "are carried forward); Bridge sums these columns.",
    )
    results = book.results
    labels = category_labels(results, MASKED)
    groups = results.price_groups
    label_of = {
        gid: category_label(labels, code)
        for gid, code in zip(groups["group_id"], groups["l2_code"], strict=True)
    }
    naive = (
        pd.Series(groups["naive_gap"].to_numpy(dtype=float))
        .groupby([label_of[g] for g in groups["group_id"]])
        .sum()
    )
    detail = results.bridge_detail
    steps = (
        pd.DataFrame(
            {
                "label": [label_of[g] for g in detail["group_id"]],
                "step": detail["step"].to_numpy(),
                "amount": detail["amount_removed"].to_numpy(dtype=float),
            }
        )
        .pivot_table(index="label", columns="step", values="amount", aggfunc="sum")
        .reindex(columns=range(1, len(STEP_NAMES) + 1))
    )
    index = sorted(set(naive.index) | set(steps.index))
    frame = pd.DataFrame({"category": index})
    frame["naive"] = naive.reindex(index).fillna(0.0).to_numpy()
    for i in range(1, len(STEP_NAMES) + 1):
        column = steps[i] if i in steps.columns else pd.Series(dtype=float)
        frame[f"step_{i}"] = column.reindex(index).fillna(0.0).to_numpy()
    cols = [
        Col("category", "Category", width=34),
        Col("naive", "Naive gap", "money"),
        *[Col(f"step_{i}", f"Step {i}: {name}", "money") for i, name in enumerate(STEP_NAMES, 1)],
    ]
    return book.table(sheet, "BridgeByCategory", cols, _frame_data(frame, cols))


def _write_spend_cube_masked(book: _Book, engine: _Engine) -> _Table:
    sheet = "Spend_Cube"
    book.furnish(sheet, "Spend cube", "In-scope spend by company and category; spend only.")
    results = book.results
    labels = category_labels(results, MASKED)
    lines = results.lines
    l2 = lines["l2_code"].astype(object)
    frame = pd.DataFrame(
        {
            "company": lines["company"].astype(str),
            "category": [category_label(labels, c) for c in l2],
            "addressable": np.where(l2.isin(engine.addressable_l2), "Yes", "No"),
            "spend": lines["amount"].astype(float),
        }
    )
    cube = frame.groupby(["company", "category", "addressable"], sort=True)["spend"].sum()
    cube = cube.reset_index()
    cols = [
        Col("company", "Company", width=10),
        Col("category", "Category", width=34),
        Col("addressable", "Addressable", width=11),
        Col("spend", "Spend", "money"),
    ]
    return book.table(sheet, "SpendCube", cols, _frame_data(cube, cols))


def _write_risk_masked(book: _Book) -> _Table:
    sheet = "Risk"
    book.furnish(
        sheet,
        "Risk guardrails",
        "Per category: cap, concentration index before and after, savings forgone. Right: the "
        "five largest vendors per category by code, the rest as one row.",
    )
    view = concentration(book.results, MASKED)
    categories = view["categories"]
    cols = [
        Col("category", "Category", width=34),
        Col("cap", "Cap", "share"),
        Col("hhi_before", "HHI before", "int"),
        Col("hhi_after", "HHI after", "int"),
        Col("savings_forgone", "Savings forgone (base)", "money"),
        Col("cap_limits", "Cap limits consolidation", width=11),
    ]
    table = book.table(sheet, "RiskCategories", cols, _frame_data(categories, cols))
    vcols = [
        Col("category", "Category (vendors)", width=34),
        Col("vendor", "Vendor", width=18),
        Col("preferred", "Preferred", width=9),
        Col("share_before", "Share before", "share"),
        Col("share_after", "Share after", "share"),
        Col("cap", "Cap (vendors)", "share"),
    ]
    book.table(
        sheet,
        "RiskVendors",
        vcols,
        _frame_data(view["vendors"], vcols),
        first_col=len(cols) + 1,
        freeze=False,
    )
    return table


def _build_masked(book: _Book, engine: _Engine) -> None:
    book.add_sheets(MASKED_SHEETS)
    _write_assumptions(book, engine, live=False)
    _write_category_settings_masked(book, engine)
    frame = _masked_opportunities(book, engine)
    book.furnish(
        "Opportunities",
        "Opportunities",
        "Aggregated to lever and category. Price and volume savings are recurring; cash release "
        "is one-time and is never added to them.",
    )
    opp = book.table(
        "Opportunities", "Opportunities", _MASKED_OPP_COLS, _frame_data(frame, _MASKED_OPP_COLS)
    )
    by_category = _write_bridge_by_category(book)
    cube = _write_spend_cube_masked(book, engine)
    risk = _write_risk_masked(book)
    year = _write_phasing(book, None)
    _write_scorecard(book)
    _write_data_quality(book)
    _write_bridge(
        book,
        f"SUM({by_category.rng('naive')})",
        lambda i: f"SUM({by_category.rng(f'step_{i}')})",
        "Steps 1-6 sum Bridge_By_Category; step 7 is the gross after step 6 less the lever-1 "
        "base saving on Opportunities.",
    )
    _write_summary(
        book,
        _sources(opp, cube, year, tier="masked", forgone=risk.rng("savings_forgone")),
        _masked_checks(by_category),
    )
    _write_readme(book, engine, MASKED_SHEETS)
