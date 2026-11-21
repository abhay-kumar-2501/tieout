"""View functions on a small generated dataset (PRD 9.2, 6.4-6.11, 7.2)."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from evaluation.scorecard import build_scorecard
from tieout import results as views
from tieout.results import NOT_IN_VIEW, Results, Unavailable
from tieout.synergy.trace import figure_value
from tieout.views.charts import _assumption_label
from tieout.views.common import category_labels

MODES = ("clean", "masked")


@pytest.fixture(scope="module")
def results(small_results: Results) -> Results:
    """The small run with a scorecard and a sensitivity curve, as the demo carries them."""
    metrics = {
        "vendor_precision": 0.99,
        "vendor_recall": 0.95,
        "item_precision": 0.98,
        "item_recall": 0.85,
        "planted_savings_recall": 0.6,
        "false_savings_rate": 0.01,
        "unit_error_catch_rate": 1.0,
    }
    card = build_scorecard(
        tuning_seeds=[1],
        held_out_seed=4,
        tool_tuning={1: metrics},
        tool_held_out=metrics,
        baseline_tuning={1: metrics},
        baseline_held_out=metrics,
    )
    curve = [{"threshold": t, "recurring_base": 1.0} for t in (80, 90)]
    sensitivity = {
        "current": {"vendor_auto": 85.0, "item_auto_cosine": 0.78, "recurring_base": 1.0},
        "curves": {"vendor_auto": curve, "item_auto_cosine": curve},
    }
    return replace(small_results, scorecard=card, sensitivity=sensitivity)


def _with_totals(results: Results, **changes: float) -> Results:
    totals = copy.deepcopy(results.totals)
    for key, value in changes.items():
        if key == "naive":
            totals["lever1"]["naive"] = value
        else:
            totals["recurring"][key] = value
    return replace(results, totals=totals)


# ---------------------------------------------------------------- numbers


def test_number_rules() -> None:
    assert views.money_range(8.2e6, 12.4e6) == "$8–12M"
    assert views.money_range(6.34e6, 9.61e6) == "$6.3–9.6M"
    assert views.money_range(9.6e6, 9.62e6) == "$9.6M"
    assert views.money_range(-1.0e6, 2.0e6) == "−$1.0M–$2.0M"
    assert views.money(31.4e6) == "$31M" and views.money(9.64e6) == "$9.6M"
    assert views.thousands(184_400) == "$184k" and views.thousands(-12_345) == "−$12k"
    assert views.percent(0.01841) == "1.8%" and views.percent(-0.05) == "−5.0%"
    assert views.unit_price(1.23456) == "$1.2346"


# ---------------------------------------------------------------- overview


def test_headline_templates_and_guards(results: Results) -> None:
    text = views.headline(results)["text"]
    assert "is defensible; the naive figure of" in text and len(text) <= 120
    held = views.headline(_with_totals(results, naive=results.totals["recurring"]["high"]))
    assert held["text"].startswith("The naive figure of") and "holds up" in held["text"]
    no_naive = views.headline(_with_totals(results, naive=0.0))["text"]
    assert "naive" not in no_naive
    nothing = _with_totals(results, low=0.0, base=0.0, high=0.0)
    assert "None of the naive figure" in views.headline(nothing)["text"]
    big = _with_totals(results, low=8.2e6, high=12.4e6, naive=31.4e6)
    assert views.headline(big)["text"] == (
        "$8–12M of run-rate savings is defensible; the naive figure of $31M is not."
    )


def test_overview_figures_keep_recurring_and_one_time_apart(results: Results) -> None:
    figures = views.overview_figures(results)
    assert [f["kind"] for f in figures] == ["recurring", "one_time", "one_time"]
    assert all(f["low"] <= f["base"] <= f["high"] for f in figures)
    off = copy.deepcopy(results.totals)
    off["checks"] |= {"lever3_enabled": False, "lever3_message": "No payment terms."}
    cash = views.overview_figures(replace(results, totals=off))[1]
    assert not cash["available"] and cash["explanation"] == "No payment terms."


def test_bridge_steps_tie_out_and_stack(results: Results) -> None:
    bars = views.bridge(results)
    assert list(bars["label"])[:2] == ["Naive figure", "Unit-of-measure errors"]
    steps = bars[bars["kind"] == "decrease"]
    assert len(steps) == 7 and (steps["amount"] <= 0).all()
    naive, lever1, lever2, final = (bars.iloc[i]["amount"] for i in (0, 8, 9, 10))
    assert naive + steps["amount"].sum() == pytest.approx(lever1, abs=0.01)
    assert final == pytest.approx(lever1 + lever2, abs=0.01)
    assert bars.iloc[10]["low"] <= final <= bars.iloc[10]["high"]
    assert np.isnan(bars.iloc[0]["low"])
    for prev, row in zip(bars.itertuples(), bars.iloc[1:].itertuples(), strict=False):
        if row.kind != "total":
            assert row.bar_base + row.bar_height == pytest.approx(max(prev.level, row.level))


def test_refused_items_resum_to_each_bridge_step(results: Results) -> None:
    bars = views.bridge(results)
    for step in range(1, 8):
        removed = -float(bars.iloc[step]["amount"])
        clean = views.refused_items(results, step, "clean")
        masked = views.refused_items(results, step, "masked")
        assert clean["amount_removed"].sum() == pytest.approx(removed, abs=0.01)
        assert masked["amount_removed"].sum() == pytest.approx(removed, abs=0.01)
        assert list(clean["amount_removed"]) == sorted(clean["amount_removed"], reverse=True)
        assert clean["reason"].notna().all()
        assert masked["figure_id"].isna().all() and "item" not in masked.columns
        for row in clean.head(2).itertuples():
            working = views.trace_for(results, row.figure_id, measure=row.measure)
            assert working["value"] == pytest.approx(row.amount_removed, abs=0.01)
    with pytest.raises(ValueError):
        views.refused_items(results, 8)


def test_lever1_items_are_clean_team_only(results: Results) -> None:
    items = views.lever1_items(results, "clean")
    opps = results.opportunities
    live = opps[(opps["lever"] == 1) & (opps["status"] == "in_range") & (opps["base"] > 0)]
    assert items["base"].sum() == pytest.approx(live["base"].sum(), abs=0.01)
    assert items.iloc[0]["base"] == items["base"].max()
    assert views.lever1_items(results, "masked") is NOT_IN_VIEW


def test_confidence_strip_and_cards(results: Results) -> None:
    strip = views.confidence_strip(results)
    assert strip["share_a"] + strip["share_b"] == pytest.approx(1.0)
    cards = views.worth_a_look(results)
    assert [c["id"] for c in cards] == ["largest_lever1", "unit_trap", "savings_forgone"]
    opps = results.opportunities
    lever1 = opps[(opps["lever"] == 1) & (opps["status"] == "in_range")]
    assert cards[0]["amount"] == pytest.approx(lever1["base"].max())
    assert cards[0]["figure_id"] in results.trace
    for card in cards:
        assert card["available"] is False or card["amount"] > 0


def test_waterfall_runs_from_baseline_to_net_spend(results: Results) -> None:
    bars = views.synergy_waterfall(results)
    baseline, lever1, lever2, net = bars["amount"]
    assert baseline + lever1 + lever2 == pytest.approx(net, abs=0.01)
    assert bars.iloc[3]["low"] <= net <= bars.iloc[3]["high"]


def test_reconciliation_text(results: Results) -> None:
    rec = views.reconciliation_text(results)
    assert len(rec["lines"]) == 2 and all("reference band" in line for line in rec["lines"])
    assert len(rec["largest"]) == (3 if rec["outside_band"] else 0)


# ---------------------------------------------------------------- charts


def test_spend_pareto_before_and_after_matching(results: Results) -> None:
    pareto = views.spend_pareto(results)
    assert pareto["parent_vendors"] == results.lines["parent_id"].nunique()
    assert pareto["vendor_records"] == len(results.vendor_map)
    for side in ("before", "after"):
        assert pareto[side]["cumulative_share"].iloc[-1] == pytest.approx(1.0)
        assert pareto[side]["spend"].is_monotonic_decreasing
    assert pareto["vendors_to_share"]["after"] <= pareto["vendors_to_share"]["before"]


def test_price_dispersion_is_clean_team_only(results: Results) -> None:
    item = results.opportunities.loc[results.opportunities["lever"] == 1, "canonical_item_id"]
    chart = views.price_dispersion(results, item.iloc[0], "clean")
    assert not chart["points"].empty and chart["points"]["price_text"].str.startswith("$").all()
    assert views.price_dispersion(results, item.iloc[0], "masked") is NOT_IN_VIEW
    assert isinstance(views.price_dispersion(results, "CI999999", "clean"), Unavailable)


def test_prioritisation_matrix(results: Results) -> None:
    for mode in MODES:
        matrix = views.prioritisation_matrix(results, mode)
        assert matrix["show_label"].sum() == min(10, len(matrix))
        assert set(matrix["wave"]) <= {1, 2, 3}
        assert matrix["complexity"].between(1, 5).all()
        opps = results.opportunities
        live = opps[(opps["status"] == "in_range") & (opps["base"] > 0)]
        assert matrix["base"].sum() == pytest.approx(live["base"].sum())


def test_phasing_by_quarter_and_year_tie_to_totals(results: Results) -> None:
    quarters = views.phasing_by_quarter(results)
    assert list(quarters["quarter"]) == list(range(1, 13))
    assert (quarters["cost"] <= 0).all() and (quarters["cash"] >= 0).all()
    years = views.phasing_by_year(results)
    phasing = results.totals["phasing"]
    for year in (1, 2, 3):
        row = years[years["year"] == year].iloc[0]
        assert row["savings"] == pytest.approx(phasing["realised"][f"year{year}"]["base"])
        assert row["savings"] == pytest.approx(
            quarters.loc[quarters["year"] == year, "savings"].sum()
        )
    total = years[years["year"] == "Total"].iloc[0]
    for case in ("low", "base", "high"):
        assert total[f"net_{case}"] == pytest.approx(phasing["net_three_year"][case], abs=0.01)


def test_concentration_shares_and_cap(results: Results) -> None:
    for mode in MODES:
        chart = views.concentration(results, mode)
        vendors = chart["vendors"]
        sums = vendors.groupby("category")[["share_before", "share_after"]].sum()
        nonzero = sums[sums["share_before"] > 0]
        assert np.allclose(nonzero["share_before"], 1.0)
        assert (vendors.groupby("category").size() <= 6).all()
        forgone = chart["categories"]["savings_forgone"].sum()
        assert forgone == pytest.approx(results.totals["lever2"]["savings_forgone"])
    masked = views.concentration(results, "masked")["categories"]
    assert set(masked["category"]) <= set(category_labels(results, "masked").values())


def test_thin_categories_merge_into_other_when_masked() -> None:
    lines = pd.DataFrame(
        {
            "l2_code": ["L01.01"] * 3 + ["L02.01"] * 2 + [None],
            "parent_id": ["A", "B", "C", "A", "B", "C"],
            "amount": [1.0] * 6,
        }
    )
    assert category_labels(Results(lines=lines), "masked") == {
        "L01.01": "L01.01 Carbon & alloy steel",
        "L02.01": "Other",
    }
    assert category_labels(Results(lines=lines), "clean")["L02.01"] == "L02.01 Bolts & screws"


def test_tornado_and_scenarios(results: Results) -> None:
    tornado = views.tornado_chart(results)
    assert 0 < len(tornado) <= 12 and tornado["swing"].is_monotonic_decreasing
    # Plain names, never the dotted path or "Lever 2 · capture · base" (PRD 6.12).
    assert not tornado["label"].str.contains("·|_|lever", case=False).any()
    assert _assumption_label("lever2.capture.base").startswith("Volume consolidation")
    table = views.scenario_table(results, {"Mine": results.assumptions})
    assert list(table["scenario"]) == [
        "Current assumptions",
        "Central (defaults)",
        "Conservative",
        "Stretch",
        "Mine",
    ]
    current, conservative, stretch, mine = (table.iloc[i] for i in (0, 2, 3, 4))
    assert current["recurring_base"] == pytest.approx(results.totals["recurring"]["base"])
    assert mine["recurring_base"] == pytest.approx(current["recurring_base"])
    assert conservative["recurring_base"] <= current["recurring_base"] <= stretch["recurring_base"]


def test_sensitivity_and_scorecard_are_demo_only(results: Results) -> None:
    curves = views.sensitivity_curves(results)
    assert list(curves["vendor_auto"]["threshold"]) == [80, 90]
    table = views.scorecard_table(results, "masked")  # the scorecard stays when masked
    assert len(table) == 7 and table["passed"].dropna().all()
    bare = replace(results, scorecard=None, sensitivity=None)
    assert isinstance(views.scorecard_table(bare), Unavailable)
    assert isinstance(views.sensitivity_curves(bare), Unavailable)


# ---------------------------------------------------------------- data and matching


def test_data_quality_and_matching_counts(results: Results) -> None:
    quality = views.data_quality_summary(results)
    assert quality["in_scope_spend"]["total"] == pytest.approx(results.totals["spend"]["baseline"])
    severities = list(quality["findings"]["severity"])
    assert severities == sorted(severities, key=["blocking", "warning", "info"].index)
    counts = views.matching_counts(results)
    assert counts["vendors"]["text"].count("→") == 2
    assert "canonical items" in counts["items"]["text"]
    assert len(views.CANNOT_SEE) == 8


def test_review_queue_views(results: Results) -> None:
    queue = views.review_queue_items(results)
    assert queue["dollars_at_stake"].is_monotonic_decreasing
    assert queue["stake_line"].str.startswith("Approving").all()
    assert set(views.review_queue_items(results, "unit_flag")["type"]) <= {"unit_flag"}
    item_pair = queue.loc[queue["type"] == "item_match", "pair_id"].iloc[0]
    focus = views.review_item(results, item_pair)
    acquirer, target = focus["records"]
    assert acquirer["company"] == "acquirer" and target["company"] == "target"
    assert set(focus["differences"]) == {"only_a", "only_b", "shared"}
    assert focus["evidence_for"] or focus["evidence_against"]
    vendor_pair = queue.loc[queue["type"].str.startswith("vendor_"), "pair_id"].iloc[0]
    assert views.review_item(results, vendor_pair)["records"][0]["fields"]["vendor_name"]
    assert isinstance(views.review_item(results, "item_match|a:x|b:y"), Unavailable)
    progress = views.review_progress(results)
    assert progress["decided"] == 0 and progress["share_cleared"] == 0.0
    for view in (views.review_queue_items, views.review_progress):
        assert view(results, view="masked") is NOT_IN_VIEW
    assert views.review_item(results, item_pair, "masked") is NOT_IN_VIEW


# ---------------------------------------------------------------- trace


def test_trace_for_every_figure_resums_to_its_value(results: Results) -> None:
    for path in results.trace_figures:
        panel = views.trace_for(results, path)
        assert panel["value"] == pytest.approx(figure_value(results.totals, path)), path
        rows = panel["rows"]
        assert rows["contribution"].sum() == pytest.approx(panel["value"], abs=0.01), path
        assert {"source_file", "source_row", "normalised_amount"} <= set(rows.columns)
        components = panel["components"]
        if not components.empty:
            assert components["amount"].sum() == pytest.approx(panel["value"], abs=0.01), path
    panel = views.trace_for(results, "levers.lever1.base")
    assert panel["copy_table"].count("\n") == len(panel["rows"]) + 1
    assert panel["copy_table"].split("\n")[0].split("\t")[:2] == ["source_file", "source_row"]


def test_trace_opens_any_node_down_to_rows(results: Results) -> None:
    opp = views.trace_for(results, "levers.lever1.base")["components"]["node"].iloc[0]
    category = views.trace_for(results, opp)
    assert category["label"] and not category["components"].empty
    deepest = views.trace_for(results, category["components"]["node"].iloc[0])
    while not deepest["components"].empty:
        deepest = views.trace_for(results, deepest["components"]["node"].iloc[0])
    assert deepest["rows"]["contribution"].sum() == pytest.approx(deepest["value"], abs=0.01)
    assert isinstance(views.trace_for(results, "nowhere"), Unavailable)


def test_masked_trace_stops_at_category_level(results: Results) -> None:
    panel = views.trace_for(results, "levers.lever1.base", view="masked")
    assert panel["rows"] is NOT_IN_VIEW and panel["copy_table"] == ""
    assert not panel["components"].empty
    first_opportunity = views.trace_for(results, "levers.lever1.base")["components"]
    category_node = first_opportunity["node"].iloc[0]
    assert views.trace_for(results, category_node, view="masked")["components"] is NOT_IN_VIEW
    assert views.trace_for(results, "lever1.bridge.step_1", view="masked") is NOT_IN_VIEW


# ---------------------------------------------------------------- masked view and tie-out


def _masked_outputs(results: Results) -> Iterator[Any]:
    """Every view's integration-office output, trace panels included."""
    m = "masked"
    yield views.headline(results, m)
    yield views.overview_figures(results, m)
    yield views.bridge(results, m)
    yield views.confidence_strip(results, m)
    yield views.worth_a_look(results, m)
    yield views.synergy_waterfall(results, m)
    for step in range(1, 8):
        yield views.refused_items(results, step, m)
    yield views.lever1_items(results, m)
    yield views.spend_pareto(results, m)
    yield views.price_dispersion(results, results.price_groups["canonical_item_id"].iloc[0], m)
    yield views.prioritisation_matrix(results, m)
    yield views.phasing_by_quarter(results, m)
    yield views.phasing_by_year(results, m)
    yield views.concentration(results, m)
    yield views.tornado_chart(results, m)
    yield views.scenario_table(results, view=m)
    yield views.reconciliation_text(results, m)
    yield views.data_quality_summary(results, m)
    yield views.matching_counts(results, m)
    yield views.review_queue_items(results, view=m)
    yield views.review_item(results, results.review_queue["pair_id"].iloc[0], m)
    yield views.review_progress(results, m)
    yield views.scorecard_table(results, m)
    yield views.sensitivity_curves(results, m)
    for node in [*results.trace_figures, *results.trace]:
        yield views.trace_for(results, node, view=m)


def _flatten(value: Any) -> Iterator[Any]:
    """Every scalar (and frame column name) inside a view output."""
    if isinstance(value, pd.DataFrame):
        yield from value.columns
        yield from value.to_numpy().ravel().tolist()
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _flatten(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _flatten(item)
    elif isinstance(value, Unavailable):
        yield value.message
    else:
        yield value


@pytest.fixture(scope="module")
def masked(results: Results) -> list[Any]:
    return list(_masked_outputs(results))


def test_masked_views_carry_no_vendor_name_or_unit_price(
    results: Results, masked: list[Any]
) -> None:
    scalars = [v for output in masked for v in _flatten(output)]
    text = "\n".join(str(v) for v in scalars if isinstance(v, str))
    numbers = {float(v) for v in scalars if isinstance(v, int | float) and not isinstance(v, bool)}

    names = set(results.vendor_map["vendor_name"].dropna()) | set(
        results.vendor_parents["parent_name"].dropna()
    )
    leaked = [name for name in names if len(name) >= 4 and name.lower() in text.lower()]
    assert not leaked, leaked[:5]
    assert not re.search(r"\b(LE\d{5}|P:[a-z])", text)  # no parent or legal-entity id
    assert not re.search(r"\bCI\d{6}\b", text)  # aggregated to category level: no items
    descriptions = {d for d in results.item_map["description"].dropna() if len(d) >= 12}
    assert not [d for d in descriptions if d in text]
    assert not re.search(r"\$\d[\d,]*\.\d{4}\b", text)  # no unit price text
    assert not [c for c in scalars if isinstance(c, str) and c.startswith("price")]
    groups = results.price_groups
    prices = pd.concat([groups[c] for c in ("p", "naive_price", "p_star", "min_price")])
    prices = pd.concat([prices, results.lines["unit_price"], results.lines["price_base"]])
    prices = prices.dropna().astype(float)
    # Prices with at least four decimals: round values (0.05) coincide with settings.
    distinctive = set(prices[(prices * 1_000 - (prices * 1_000).round()).abs() > 1e-6])
    assert not numbers & distinctive, sorted(numbers & distinctive)[:5]


def test_masked_vendor_codes_follow_combined_spend(results: Results) -> None:
    codes = views.vendor_codes(results)
    spend = results.lines.groupby("parent_id")["amount"].sum()
    ordered = sorted(codes, key=lambda p: codes[p])
    assert spend.loc[ordered].is_monotonic_decreasing
    assert re.fullmatch(r"Vendor 0*1", codes[ordered[0]])


def test_every_total_shown_by_views_equals_totals_to_the_dollar(results: Results) -> None:
    totals = results.totals
    for mode in MODES:
        shown: list[tuple[float, str]] = []
        head = views.headline(results, mode)
        shown += [(head[c], f"recurring.{c}") for c in ("low", "base", "high")]
        shown.append((head["naive"], "lever1.naive"))
        for figure in views.overview_figures(results, mode):
            node = figure["figure_id"].rsplit(".", 1)[0]
            shown += [(figure[c], f"{node}.{c}") for c in ("low", "base", "high")]
        for bar in views.bridge(results, mode).itertuples():
            shown.append((abs(bar.amount), bar.figure_id))
        shown.append((views.bridge(results, mode).iloc[-1]["low"], "recurring.low"))
        for bar in views.synergy_waterfall(results, mode).itertuples():
            shown.append((abs(bar.amount), bar.figure_id))
        strip = views.confidence_strip(results, mode)
        shown += [(strip[k], path) for k, path in strip["figure_ids"].items()]
        years = views.phasing_by_year(results, mode).set_index("year")
        for year in (1, 2, 3):
            shown.append((years.loc[year, "savings"], f"phasing.realised.year{year}.base"))
        shown.append((years.loc["Total", "net_base"], "phasing.net_three_year.base"))
        rec = views.reconciliation_text(results, mode)
        shown += [(rec["total_spend"], "spend.baseline"), (rec["base"], "recurring.base")]
        current = views.scenario_table(results, view=mode).iloc[0]
        shown += [
            (current["recurring_base"], "recurring.base"),
            (current["cash_base"], "one_time.cash.base"),
            (current["one_time_cost_base"], "one_time.costs.base"),
        ]
        chart = views.concentration(results, mode)["categories"]
        shown.append((chart["savings_forgone"].sum(), "lever2.savings_forgone"))
        for value, path in shown:
            assert round(value) == round(figure_value(totals, path)), (mode, path)


def test_view_outputs_are_plain_data(masked: list[Any]) -> None:
    """Dictionaries, frames, numbers and text only: JSON-serialisable outside the frames."""

    def plain(value: Any) -> Any:
        if isinstance(value, pd.DataFrame):
            return value.to_dict("records")
        if isinstance(value, Unavailable):
            return value.message
        raise TypeError(type(value).__name__)

    json.dumps(masked, default=plain)


def test_bulk_approve_preview_counts_the_pairs_above_a_score(results: Results) -> None:
    from tieout.views import bulk_approve_preview

    whole = bulk_approve_preview(results, "vendor_match", None, "clean")
    pending = results.review_queue.query("type == 'vendor_match' and status == 'pending'")
    assert whole["count"] == len(pending) and whole["score_low"] <= whole["score_high"]
    middle = float(pending["score"].median())
    part = bulk_approve_preview(results, "vendor_match", middle, "clean")
    assert 0 < part["count"] <= whole["count"]
    assert part["dollars_at_stake"] <= whole["dollars_at_stake"]
    assert len(part["pair_ids"]) == part["count"]
    assert isinstance(bulk_approve_preview(results, "unit_flag", None, "clean"), Unavailable)
    assert isinstance(bulk_approve_preview(results, "vendor_match", None, "masked"), Unavailable)


def test_review_item_opens_pairs_whose_record_key_contains_a_pipe(results: Results) -> None:
    queue = results.review_queue.iloc[:1].copy()
    queue["pair_id"] = queue["pair_id"] + "|some maker"  # as a key with a pipe makes it
    odd = replace(results, review_queue=queue)
    item = views.review_item(odd, queue["pair_id"].iloc[0], "clean")
    assert not isinstance(item, Unavailable) and len(item["records"]) == 2
    assert views.bulk_approve_preview(odd, queue["type"].iloc[0], None, "clean")["count"] == 1
