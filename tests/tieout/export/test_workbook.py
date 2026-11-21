"""The formula-live workbook (PRD 7.1, 10.2): structure, tie-out, formulas, masking."""

from __future__ import annotations

import copy
import io
import re
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import openpyxl
import pandas as pd
import pytest
from xlsx_formulas import EXCEL_ERRORS, FUNCTIONS, Workbook, names_in, relative_close, sheets_in

from tieout import results as views
from tieout.export.workbook import (
    _ASSUMPTIONS,
    CHECK_NAME,
    CLEAN_SHEETS,
    MASKED_SHEETS,
    SUMMARY_NAMES,
    build_workbook,
)
from tieout.pipeline import recompute
from tieout.results import Results

MODES = ("clean", "masked")
CENT = 0.01
#: Assumption cells changed in the recalculation tests: every kind of live input.
CHANGES = {
    "Pi1_Same_Base": 0.80,
    "Pi1_Switch_High": 0.65,
    "Pi1_Same_Low": 0.45,
    "Pi2_Low": 0.30,
    "Pi2_Base": 0.65,
    "Discount_MRO": 0.06,
    "Discount_Engineered": 0.025,
    "Pi3_Base": 0.60,
    "Switch_Cost_Fixed": 40_000.0,
    "Switch_Cost_Pct": 0.02,
    "Cost_Of_Capital": 0.10,
    "Ramp_Year1": 0.50,
    "Ramp_Year2": 0.90,
}
DEMO = Path(__file__).resolve().parents[3] / "data" / "demo" / "results"


@pytest.fixture(scope="module")
def results(small_results: Results) -> Results:
    return small_results


@pytest.fixture(scope="module")
def books(results: Results) -> dict[str, bytes]:
    return {mode: build_workbook(results, mode) for mode in MODES}


@pytest.fixture(scope="module")
def parsed(books: dict[str, bytes]) -> dict[str, Workbook]:
    return {mode: Workbook(data) for mode, data in books.items()}


def _with_changes(results: Results, changes: dict[str, float]) -> dict[str, Any]:
    new = copy.deepcopy(results.assumptions)
    paths = {a.name: a.path for a in _ASSUMPTIONS}
    for name, value in changes.items():
        node = new
        for key in paths[name][:-1]:
            node = node[key]
        node[paths[name][-1]] = value
    return new


def _cases(node: dict[str, Any]) -> dict[str, float]:
    return {c: float(node[c]) for c in ("low", "base", "high")}


def _expected(totals: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Summary figures from ``totals``, keyed like ``SUMMARY_NAMES``."""
    realised = totals["phasing"]["realised"]
    net3 = totals["phasing"]["net_three_year"]
    return {
        "Recurring": _cases(totals["recurring"]),
        "Lever1": _cases(totals["levers"]["lever1"]),
        "Lever2": _cases(totals["levers"]["lever2"]),
        "Naive": {"base": totals["lever1"]["naive"]},
        "TierA": {"base": totals["lever1"]["tier_a"]["base"]},
        "TierB": {"base": totals["lever1"]["tier_b"]["base"]},
        "Pending_Upside": {"base": totals["lever1"]["upside_pending_review"]},
        "Savings_Forgone": {"base": totals["lever2"]["savings_forgone"]},
        "Cash": _cases(totals["one_time"]["cash"]),
        "Financing": _cases(totals["memo"]["financing_value"]),
        "OneTime_Cost": _cases(totals["one_time"]["costs"]),
        **{f"Realised_Y{y}": _cases(realised[f"year{y}"]) for y in (1, 2, 3)},
        "Window_Cost": {
            c: net3[c] - sum(realised[f"year{y}"][c] for y in (1, 2, 3))
            for c in ("low", "base", "high")
        },
        "Net3Y": _cases(net3),
        "Baseline": {"base": totals["spend"]["baseline"]},
        "Addressable": {"base": totals["spend"]["addressable"]},
        "Net_Run_Rate": _cases(totals["spend"]["net_run_rate"]),
        "Share_Total": {"base": totals["reconciliation"]["total_spend"]["share"]},
        "Share_Addressable": {"base": totals["reconciliation"]["addressable_spend"]["share"]},
    }


def _assert_formulas_reproduce_cache(wb: Workbook) -> int:
    count = 0
    for key, formula in wb.formula_cells():
        got, cached = wb.value(key), wb.cached.get(key)
        if isinstance(cached, str) or isinstance(got, str):
            assert got == cached, (key, formula)
        else:
            assert relative_close(got, cached or 0.0) or abs(got - (cached or 0.0)) <= CENT, (
                key,
                formula,
                got,
                cached,
            )
        count += 1
    return count


def _view_figures(results: Results, mode: str) -> dict[str, float]:
    """Every headline figure the views display, under its Summary or Bridge name."""
    out: dict[str, float] = {}
    head = views.headline(results, mode)
    out |= {
        "Recurring_Low": head["low"],
        "Recurring_Base": head["base"],
        "Recurring_High": head["high"],
        "Naive": head["naive"],
    }
    names = {"run_rate": "Recurring", "cash": "Cash", "cost": "OneTime_Cost"}
    for figure in views.overview_figures(results, mode):
        for case in ("low", "base", "high"):
            out[f"{names[figure['id']]}_{case.title()}"] = figure[case]
    bars = views.bridge(results, mode).set_index("step")
    out["Bridge_Naive"] = bars.loc[0, "amount"]
    for step in range(1, 8):
        out[f"Bridge_Step{step}"] = -bars.loc[step, "amount"]
    out["Lever1_Base"] = bars.loc[8, "amount"]
    out["Lever2_Base"] = bars.loc[9, "amount"]
    out["Recurring_Low"] = bars.loc[10, "low"]
    out["Recurring_High"] = bars.loc[10, "high"]
    fall = views.synergy_waterfall(results, mode).set_index("label")
    out["Baseline"] = fall.loc["In-scope spend (baseline)", "amount"]
    out["Net_Run_Rate_Base"] = fall.loc["Net run-rate spend", "amount"]
    out["Net_Run_Rate_Low"] = fall.loc["Net run-rate spend", "high"]
    out["Net_Run_Rate_High"] = fall.loc["Net run-rate spend", "low"]
    years = views.phasing_by_year(results, mode).set_index("year")
    for y in (1, 2, 3):
        out[f"Realised_Y{y}_Base"] = years.loc[y, "savings"]
        out[f"Realised_Y{y}_Low"] = years.loc[y, "savings_low"]
        out[f"Realised_Y{y}_High"] = years.loc[y, "savings_high"]
    out["Window_Cost_Base"] = years.loc["Total", "cost"]
    for case in ("low", "base", "high"):
        out[f"Net3Y_{case.title()}"] = years.loc["Total", f"net_{case}"]
    strip = views.confidence_strip(results, mode)
    out |= {"TierA": strip["tier_a"], "TierB": strip["tier_b"]}
    out["Pending_Upside"] = strip["pending_review"]
    rec = views.reconciliation_text(results, mode)
    out |= {"Addressable": rec["addressable_spend"], "Recurring_Base": rec["base"]}
    return out


# ---------------------------------------------------------------- structure


@pytest.mark.parametrize("mode", MODES)
def test_workbook_opens_with_expected_sheets_names_and_check(
    books: dict[str, bytes], mode: str
) -> None:
    data = books[mode]
    assert isinstance(data, bytes) and data[:2] == b"PK"
    book = openpyxl.load_workbook(io.BytesIO(data))
    assert tuple(book.sheetnames) == (CLEAN_SHEETS if mode == "clean" else MASKED_SHEETS)
    names = set(book.defined_names)
    expected = {a.name for a in _ASSUMPTIONS} | {CHECK_NAME, "Bridge_Naive", "Bridge_Residual"}
    expected |= {f"Bridge_Step{i}" for i in range(1, 8)}
    expected |= {name for cases in SUMMARY_NAMES.values() for name in cases.values()}
    assert expected <= names
    values = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    sheet, cell = next(iter(book.defined_names[CHECK_NAME].destinations))
    assert values[sheet][cell.replace("$", "")].value == "OK"
    assert {ws["A1"].value for ws in values.worksheets} == {"Tie-Out"}  # not a demo run


def test_demo_runs_carry_the_illustrative_label_in_a1(results: Results) -> None:
    demo = replace(results, meta={**results.meta, "scenario": "demo"})
    values = openpyxl.load_workbook(io.BytesIO(build_workbook(demo, "masked")), data_only=True)
    assert {ws["A1"].value for ws in values.worksheets} == {"Illustrative — synthetic data"}


def test_masked_workbook_omits_the_detail_tabs(books: dict[str, bytes]) -> None:
    sheets = set(openpyxl.load_workbook(io.BytesIO(books["masked"])).sheetnames)
    omitted = {"Price_Variance", "Vendor_Map", "Item_Map", "Review_Log", "Bridge_Detail"}
    assert not sheets & (omitted | {"Payment_Terms", "Links"})
    assert "Bridge_By_Category" in sheets


def test_detail_tabs_are_tables_with_frozen_headers(books: dict[str, bytes]) -> None:
    book = openpyxl.load_workbook(io.BytesIO(books["clean"]))
    for sheet in ("Opportunities", "Spend_Cube", "Price_Variance", "Bridge_Detail", "Risk"):
        ws = book[sheet]
        assert ws.tables, sheet
        assert ws.freeze_panes == "A6", sheet


def test_inputs_are_blue_and_formulas_black(books: dict[str, bytes]) -> None:
    book = openpyxl.load_workbook(io.BytesIO(books["clean"]))
    for item in _ASSUMPTIONS:
        sheet, cell = next(iter(book.defined_names[item.name].destinations))
        color = book[sheet][cell.replace("$", "")].font.color
        rgb = color.rgb if color is not None else None
        assert (rgb == "FF0000FF") == item.live, item.name
    sheet, cell = next(iter(book.defined_names["Recurring_Base"].destinations))
    color = book[sheet][cell.replace("$", "")].font.color
    assert color is not None and color.rgb == "FF000000"


def test_build_is_deterministic(results: Results, books: dict[str, bytes]) -> None:
    assert build_workbook(results, "clean") == books["clean"]


def test_default_view_is_the_runs_own_mode(results: Results, books: dict[str, bytes]) -> None:
    masked_run = replace(results, meta={**results.meta, "view": "masked"})
    assert build_workbook(masked_run) == build_workbook(results, "masked")
    with pytest.raises(ValueError):
        build_workbook(results, "public")


# ---------------------------------------------------------------- tie-out


@pytest.mark.parametrize("mode", MODES)
def test_headline_figures_tie_to_the_view_functions(
    results: Results, parsed: dict[str, Workbook], mode: str
) -> None:
    wb = parsed[mode]
    for name, value in _view_figures(results, mode).items():
        assert abs(wb.cached_name(name) - value) <= CENT, name
    expected = _expected(results.totals)
    for key, cases in SUMMARY_NAMES.items():
        for case, name in cases.items():
            assert abs(wb.cached_name(name) - expected[key][case]) <= CENT, name


@pytest.mark.parametrize("mode", MODES)
def test_phasing_tables_tie_to_the_views(
    results: Results, parsed: dict[str, Workbook], mode: str
) -> None:
    wb = parsed[mode]
    years = views.phasing_by_year(results, mode)
    rows = wb.table_rows("PhasingYear")
    for row, (_, view) in zip(rows, years.iterrows(), strict=True):
        assert abs(row["Realised savings base"] - view["savings"]) <= CENT
        assert abs(row["One-time cost base"] - view["cost"]) <= CENT
        for w in (1, 2, 3):
            assert abs(row[f"Wave {w} savings (base)"] - view[f"wave_{w}"]) <= CENT
    quarters = views.phasing_by_quarter(results, mode)
    for row, (_, view) in zip(wb.table_rows("PhasingQuarter"), quarters.iterrows(), strict=True):
        assert abs(row["Realised savings (base)"] - view["savings"]) <= CENT
        assert abs(row["One-time cost (base)"] - view["cost"]) <= CENT
        assert abs(row["Cash release (base, one-time)"] - view["cash"]) <= CENT


def test_masked_tables_tie_to_the_masked_views(
    results: Results, parsed: dict[str, Workbook]
) -> None:
    wb = parsed["masked"]
    rows = {(r["Lever"], r["Opportunity"]): r for r in wb.table_rows("Opportunities")}
    matrix = views.prioritisation_matrix(results, "masked")
    assert len(matrix)
    column = {1: "Price saving base (lever 1)", 2: "Volume saving base (lever 2)"}
    column[3] = "Cash release base (lever 3, one-time)"
    for item in matrix.itertuples(index=False):
        assert abs(rows[(item.lever, item.label)][column[item.lever]] - item.base) <= CENT
    risk = views.concentration(results, "masked")["categories"].set_index("category")
    for row in wb.table_rows("RiskCategories"):
        assert (
            abs(row["Savings forgone (base)"] - risk.loc[row["Category"], "savings_forgone"])
            <= CENT
        )


# ---------------------------------------------------------------- formulas without Excel


@pytest.mark.parametrize("mode", MODES)
def test_every_formula_reproduces_its_stored_value(parsed: dict[str, Workbook], mode: str) -> None:
    wb = parsed[mode]
    wb.overrides.clear()
    wb.reset()
    assert _assert_formulas_reproduce_cache(wb) > (1000 if mode == "clean" else 50)


def _assert_recalculation_matches_recompute(results: Results, wb: Workbook) -> None:
    wb.overrides.clear()
    for name, value in CHANGES.items():
        wb.set_value(wb.name_cell(name), value)
    updated = recompute(results, _with_changes(results, CHANGES))
    expected = _expected(updated.totals)
    for key, cases in SUMMARY_NAMES.items():
        for case, name in cases.items():
            assert abs(wb.value(wb.name_cell(name)) - expected[key][case]) <= CENT, name
    for step in range(1, 8):
        want = updated.totals["lever1"]["bridge"][f"step_{step}"]
        assert abs(wb.value(wb.name_cell(f"Bridge_Step{step}")) - want) <= CENT
    opps = updated.opportunities.set_index("opportunity_id")
    for row in wb.table_rows("Opportunities", evaluated=True):
        lever = row["Lever"]
        label = {1: "Price saving", 2: "Volume saving", 3: "Cash release"}[lever]
        for case in ("low", "base", "high"):
            header = next(h for h in row if h.startswith(f"{label} {case} "))
            assert abs((row[header] or 0.0) - opps.loc[row["Opportunity"], case]) <= CENT
    assert wb.value(wb.name_cell(CHECK_NAME)) == "OK"  # the check is internal, not vs export
    wb.overrides.clear()
    wb.reset()


def test_changing_assumptions_reproduces_recompute(
    results: Results, parsed: dict[str, Workbook]
) -> None:
    _assert_recalculation_matches_recompute(results, parsed["clean"])


@pytest.mark.parametrize("mode", MODES)
def test_corrupting_a_detail_cell_breaks_the_check(parsed: dict[str, Workbook], mode: str) -> None:
    """A price saving edited by hand on Opportunities no longer ties to the bridge or groups."""
    wb = parsed[mode]
    wb.overrides.clear()
    wb.reset()
    sheet, ref = wb.tables["Opportunities"]
    header_row = int(re.search(r"\d+", ref).group())
    column = next(
        c
        for (s, r, c), v in wb.cells.items()
        if s == sheet and r == header_row and v == "Price saving base (lever 1)"
    )
    row = next(
        r
        for (s, r, c), v in wb.cached.items()
        if s == sheet and c == column and r > header_row and isinstance(v, float) and v > 0
    )
    wb.set_value((sheet, row, column), wb.cached[(sheet, row, column)] + 1_000.0)
    try:
        check = wb.value(wb.name_cell(CHECK_NAME))
        assert isinstance(check, float) and check >= 999.0
    finally:
        wb.overrides.clear()
        wb.reset()


@pytest.fixture(scope="module")
def ramp_results(results: Results) -> Results:
    """No contract dates and no payment terms: global ramp, lever 3 switched off."""
    lines = results.lines.copy()
    lines["contract_end_date"] = pd.NaT
    lines["payment_terms_days"] = np.nan
    lines["payment_date"] = pd.NaT
    stripped = replace(results, lines=lines, synergy_cache=None)
    return recompute(stripped, results.assumptions)


def test_global_ramp_and_no_lever3_workbook(ramp_results: Results) -> None:
    assert ramp_results.totals["phasing"]["method"] == "global_ramp"
    assert not ramp_results.totals["checks"]["lever3_enabled"]
    data = build_workbook(ramp_results, "clean")
    wb = Workbook(data)
    assert wb.cached_name(CHECK_NAME) == "OK"
    assert any("Ramp_Year1" in f for _, f in wb.formula_cells())
    _assert_formulas_reproduce_cache(wb)
    _assert_recalculation_matches_recompute(ramp_results, wb)


# ---------------------------------------------------------------- errors and references


@pytest.mark.parametrize("mode", MODES)
def test_no_formula_errors_and_every_reference_exists(
    parsed: dict[str, Workbook], mode: str
) -> None:
    wb = parsed[mode]
    for value in wb.cached.values():
        assert not (isinstance(value, str) and value.strip() in EXCEL_ERRORS)
    for key, formula in wb.formula_cells():
        assert sheets_in(formula) <= set(wb.sheets), (key, formula)
        unknown = names_in(formula) - set(wb.names) - FUNCTIONS
        assert not unknown, (key, formula, unknown)
        wb.parsed(key[0], formula)  # within the evaluator's grammar


# ---------------------------------------------------------------- masking


def _strings(wb: Workbook) -> list[str]:
    return [v for v in wb.cells.values() if isinstance(v, str)]


def test_masked_workbook_has_no_vendor_names_items_or_unit_prices(
    results: Results, parsed: dict[str, Workbook]
) -> None:
    wb = parsed["masked"]
    text = "\n".join(_strings(wb))
    vendors = {str(v) for v in results.vendor_map["vendor_name"].dropna() if len(str(v)) >= 5}
    descriptions = {str(v) for v in results.item_map["description"].dropna() if len(str(v)) >= 8}
    assert vendors and descriptions
    assert not [v for v in vendors if v in text]
    assert not [d for d in descriptions if d in text]
    assert not re.search(r"\bCI\d{4,}\b", text)  # canonical item ids
    assert not re.search(r"\bLE\d{4,}\b", text)  # legal entities
    assert not re.search(r"\$\d[\d,]*\.\d{4}\b", text)  # unit-price text
    prices = set(results.price_groups["p"].dropna().round(6)) - {0.0}
    numbers = {round(v, 6) for v in wb.cells.values() if isinstance(v, float)}
    assert not prices & numbers
    clean_text = "\n".join(_strings(parsed["clean"]))
    assert any(v in clean_text for v in vendors)  # the scan would catch a leak


# ---------------------------------------------------------------- LibreOffice


_RECALC_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
 xmlns:xs="http://www.w3.org/2001/XMLSchema"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load">
<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>
"""


@pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice (soffice) is not installed"
)
@pytest.mark.parametrize("mode", MODES)
def test_libreoffice_recalculation_matches_stored_values(
    books: dict[str, bytes], parsed: dict[str, Workbook], mode: str, tmp_path: Path
) -> None:
    """Headless LibreOffice with recalculation on load forced on (PRD 7.1)."""
    profile = tmp_path / "profile"
    (profile / "user").mkdir(parents=True)
    (profile / "user" / "registrymodifications.xcu").write_text(_RECALC_PROFILE)
    source = tmp_path / "in" / f"{mode}.xlsx"
    source.parent.mkdir()
    source.write_bytes(books[mode])
    out = tmp_path / "out"
    subprocess.run(
        [
            str(shutil.which("soffice")),
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(out),
            str(source),
        ],
        check=True,
        timeout=600,
        capture_output=True,
    )
    recalculated = Workbook((out / source.name).read_bytes())
    stored = parsed[mode]
    for key, _ in stored.formula_cells():
        before, after = stored.cached.get(key), recalculated.cached.get(key)
        if isinstance(before, str):
            assert after == before, key
        else:
            assert relative_close(after or 0.0, before or 0.0), (key, before, after)


# ---------------------------------------------------------------- demo


@pytest.mark.slow
def test_demo_workbooks_build_fast_tie_out_and_recalculate() -> None:
    demo = Results.load(DEMO)
    sizes = {}
    for mode in MODES:
        start = time.perf_counter()
        data = build_workbook(demo, mode)
        seconds = time.perf_counter() - start
        sizes[mode] = len(data)
        assert seconds < 60, (mode, seconds)
        wb = Workbook(data)
        assert wb.cached_name(CHECK_NAME) == "OK"
        for name, value in _view_figures(demo, mode).items():
            assert abs(wb.cached_name(name) - value) <= CENT, name
        _assert_formulas_reproduce_cache(wb)
        if mode == "clean":
            _assert_recalculation_matches_recompute(demo, wb)
    assert sizes["clean"] < 20_000_000 and sizes["masked"] < 1_000_000
