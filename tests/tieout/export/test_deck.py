"""The eight-slide deck (PRD 7.2): structure, tie-out to the views and the masked view."""

from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import replace
from itertools import combinations

import pytest
from pptx import Presentation
from pptx.util import Inches

from tieout import results as views
from tieout import theme
from tieout.export.deck import SLIDE_COUNT, build_deck
from tieout.results import Results
from tieout.views.common import unit_price

MODES = ("clean", "masked")


@pytest.fixture(scope="module")
def results(small_results: Results) -> Results:
    return small_results


@pytest.fixture(scope="module")
def decks(results: Results) -> dict[str, bytes]:
    return {view: build_deck(results, view) for view in MODES}


def load(data: bytes) -> Presentation:
    return Presentation(io.BytesIO(data))


def shape_text(shape) -> str:
    parts: list[str] = []
    if shape.has_text_frame:
        parts.append(shape.text_frame.text)
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            parts.extend(cell.text_frame.text for cell in row.cells)
    return "\n".join(parts)


def slide_text(slide, notes: bool = False) -> str:
    text = "\n".join(shape_text(s) for s in slide.shapes)
    return text + ("\n" + slide.notes_slide.notes_text_frame.text if notes else "")


def title_of(slide) -> str:
    return next(s for s in slide.shapes if s.name == "Title").text_frame.text


def shape_named(slide, prefix: str):
    return next(s for s in slide.shapes if s.name.startswith(prefix))


# ---------------------------------------------------------------- structure


@pytest.mark.parametrize("view", MODES)
def test_eight_slides_16_9(decks: dict[str, bytes], view: str) -> None:
    prs = load(decks[view])
    assert len(prs.slides) == SLIDE_COUNT == 8
    assert prs.slide_width == Inches(13.333)
    assert prs.slide_height == Inches(7.5)


@pytest.mark.parametrize("view", MODES)
def test_titles_and_no_empty_placeholders(decks: dict[str, bytes], view: str) -> None:
    for slide in load(decks[view]).slides:
        title = title_of(slide)
        assert title.strip()
        assert len(title) <= 120
        for shape in slide.placeholders:
            assert shape.has_text_frame and shape.text_frame.text.strip()
        assert not re.search(r"Click to add|\{\{", slide_text(slide, notes=True))


@pytest.mark.parametrize("view", MODES)
def test_every_slide_has_source_footer_and_page_number(decks: dict[str, bytes], view: str) -> None:
    for number, slide in enumerate(load(decks[view]).slides, start=1):
        assert shape_named(slide, "Source").text_frame.text.startswith("Source:")
        assert "Workbook:" in shape_named(slide, "Source").text_frame.text
        assert shape_named(slide, "Page number").text_frame.text == str(number)


@pytest.mark.parametrize("view", MODES)
def test_shapes_stay_on_the_slide_and_do_not_overlap(decks: dict[str, bytes], view: str) -> None:
    prs = load(decks[view])
    for number, slide in enumerate(prs.slides, start=1):
        boxes = [(s.name, s.left, s.top, s.left + s.width, s.top + s.height) for s in slide.shapes]
        for name, left, top, right, bottom in boxes:
            assert left >= 0 and top >= 0, (number, name)
            assert right <= prs.slide_width and bottom <= prs.slide_height, (number, name)
        for a, b in combinations(boxes, 2):
            apart = a[3] <= b[1] or b[3] <= a[1] or a[4] <= b[2] or b[4] <= a[2]
            assert apart, (number, a[0], b[0])


def test_illustrative_label_in_every_footer_for_the_demo(results: Results) -> None:
    demo = replace(results, meta={**results.meta, "scenario": "demo"})
    other = replace(results, meta={**results.meta, "scenario": "upload"})
    for slide in load(build_deck(demo)).slides:
        assert theme.ILLUSTRATIVE_LABEL in shape_named(slide, "Footer").text_frame.text
    for slide in load(build_deck(other)).slides:
        assert theme.ILLUSTRATIVE_LABEL not in slide_text(slide)


def test_default_view_is_the_runs_own(results: Results, decks: dict[str, bytes]) -> None:
    default = load(build_deck(results))
    assert "Clean-team view" in shape_named(default.slides[0], "Footer").text_frame.text
    masked_run = replace(results, meta={**results.meta, "view": "masked"})
    first = load(build_deck(masked_run)).slides[0]
    assert "Integration-office view" in shape_named(first, "Footer").text_frame.text


# ---------------------------------------------------------------- tie-out


@pytest.mark.parametrize("view", MODES)
def test_headline_numbers_match_the_views(
    results: Results, decks: dict[str, bytes], view: str
) -> None:
    slides = list(load(decks[view]).slides)
    head = views.headline(results, view)
    assert head["range_text"] in title_of(slides[0])
    assert title_of(slides[1]) == head["text"]

    spend = views.data_quality_summary(results, view)["in_scope_spend"]
    assert views.money(spend["total"]) in slide_text(slides[0])
    assert views.money(spend["total"]) in slide_text(slides[2])

    for figure in views.overview_figures(results, view):
        if figure["available"]:
            assert figure["text"] in slide_text(slides[1])
    assert views.confidence_strip(results, view)["text"] in slide_text(slides[1])

    pareto = views.spend_pareto(results, view)
    title3 = title_of(slides[2])
    assert f"{pareto['vendor_records']:,}" in title3
    assert f"{pareto['parent_vendors']:,}" in title3
    assert f"{pareto['vendors_to_share']['after']:,}" in title3
    assert views.matching_counts(results, view)["vendors"]["text"] in slide_text(slides[2])

    frame = views.bridge(results, view)
    title4 = title_of(slides[3])
    assert views.money(float(frame["amount"].iloc[0])) in title4
    assert views.money(float(frame["amount"].iloc[-3])) in title4

    figures = {f["id"]: f for f in views.overview_figures(results, view)}
    text5 = slide_text(slides[4])
    assert head["range_text"] in title_of(slides[4])
    assert figures["cost"]["text"] in text5
    if figures["cash"]["available"]:
        assert figures["cash"]["text"] in text5

    years = views.phasing_by_year(results, view)
    year3 = float(years.loc[years["year"] == 3, "savings"].iloc[0])
    net = float(years.loc[years["year"] == "Total", "net_base"].iloc[0])
    assert views.money(year3) in title_of(slides[5])
    assert views.money(net) in title_of(slides[5])
    top = views.prioritisation_matrix(results, view).head(5)
    table = slide_text(slides[5])
    for row in top.itertuples(index=False):
        assert views.thousands(float(row.base)) in table
        assert str(row.label)[:30] in table

    risk = views.concentration(results, view)["categories"]
    assert views.money(float(risk["savings_forgone"].sum())) in title_of(slides[6])
    for row in risk.head(5).itertuples(index=False):
        assert views.thousands(float(row.savings_forgone)) in slide_text(slides[6])
    for item in views.CANNOT_SEE:
        assert item in slide_text(slides[6])

    counts = views.matching_counts(results, view)
    assert f"{counts['vendors']['legal_entities']:,}" in title_of(slides[7])
    assert counts["items"]["text"] in slide_text(slides[7])


@pytest.mark.parametrize("view", MODES)
def test_chart_series_are_the_views_series(
    results: Results, decks: dict[str, bytes], view: str
) -> None:
    slides = list(load(decks[view]).slides)
    for slide, name, frame in (
        (slides[3], "Bridge chart", views.bridge(results, view)),
        (slides[4], "Waterfall chart", views.synergy_waterfall(results, view)),
    ):
        chart = shape_named(slide, name).chart
        plot = chart.plots[0]
        assert list(plot.categories) == list(frame["label"])
        base, amount = plot.series[0], plot.series[1]
        assert [round(v, 4) for v in base.values] == [round(v, 4) for v in frame["bar_base"]]
        assert [round(v, 4) for v in amount.values] == [round(v, 4) for v in frame["bar_height"]]

    years = views.phasing_by_year(results, view)
    years = years[years["year"] != "Total"]
    phasing = shape_named(slides[5], "Phasing chart").chart.plots[0]
    for wave, series in zip((1, 2, 3), list(phasing.series)[:3], strict=True):
        assert [round(v, 4) for v in series.values] == [
            round(float(v), 4) for v in years[f"wave_{wave}"]
        ]
    matrix = views.prioritisation_matrix(results, view)
    bubbles = shape_named(slides[5], "Prioritisation matrix").chart.plots[0]
    assert sum(len(list(s.values)) for s in bubbles.series) == len(matrix)


@pytest.mark.parametrize("view", MODES)
def test_scorecard_slide_matches_the_view(
    results: Results, decks: dict[str, bytes], view: str
) -> None:
    text = slide_text(list(load(decks[view]).slides)[7])
    card = views.scorecard_table(results, view)
    assert isinstance(card, views.Unavailable)  # the small run carries no scorecard
    assert "scorecard omitted" in text.lower()


def test_scorecard_values_appear_when_present(results: Results) -> None:
    metrics = {
        "vendor_precision": 0.99,
        "vendor_recall": 0.95,
        "item_precision": 0.98,
        "item_recall": 0.85,
        "planted_savings_recall": 0.6,
        "false_savings_rate": 0.01,
        "unit_error_catch_rate": 1.0,
    }
    from evaluation.scorecard import build_scorecard

    card = build_scorecard(
        tuning_seeds=[1],
        held_out_seed=4,
        tool_tuning={1: metrics},
        tool_held_out=metrics,
        baseline_tuning={1: metrics},
        baseline_held_out=metrics,
    )
    with_card = replace(results, scorecard=card)
    for view in MODES:
        slide = list(load(build_deck(with_card, view)).slides)[7]
        text = slide_text(slide)
        table = views.scorecard_table(with_card, view)
        for row in table.itertuples(index=False):
            assert row.label in text
            assert views.percent(float(row.tool)) in text


# ---------------------------------------------------------------- masked


def raw_text(data: bytes) -> str:
    """Every XML part of the package (slides, notes, charts and their data), as one string."""
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        for name in package.namelist():
            if name.endswith((".xml", ".rels")):
                parts.append(package.read(name).decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def sensitive_strings(results: Results) -> set[str]:
    names = set(results.vendor_map["vendor_name"].dropna().astype(str))
    names |= set(results.item_map["description"].dropna().astype(str))
    names = {n for n in names if len(n) >= 6 and re.fullmatch(r"[A-Za-z0-9 .,/\-]+", n)}
    prices = {unit_price(float(p)) for p in results.price_groups["p"].dropna()}
    return names | {p for p in prices if p}


def test_masked_deck_has_no_vendor_name_item_description_or_unit_price(
    results: Results, decks: dict[str, bytes]
) -> None:
    sensitive = sensitive_strings(results)
    assert sensitive
    masked = raw_text(decks["masked"])
    leaks = sorted(s for s in sensitive if s in masked)
    assert not leaks[:5]
    prs = load(decks["masked"])
    shown = "\n".join(slide_text(s, notes=True) for s in prs.slides)
    assert not [s for s in sensitive if s in shown][:5]


def test_clean_deck_does_show_names(results: Results, decks: dict[str, bytes]) -> None:
    """Guards the masked scan: the same scan does find item descriptions in the clean deck."""
    sensitive = sensitive_strings(results)
    assert any(s in raw_text(decks["clean"]) for s in sensitive)


def test_masked_deck_says_it_is_a_presentation_mode(decks: dict[str, bytes]) -> None:
    first = slide_text(load(decks["masked"]).slides[0])
    assert "Integration-office view" in first
    assert "not a security control" in first


# ---------------------------------------------------------------- demo


@pytest.mark.slow
@pytest.mark.parametrize("view", MODES)
def test_demo_deck(view: str) -> None:
    demo = Results.load("data/demo/results")
    start = time.perf_counter()
    data = build_deck(demo, view)
    assert time.perf_counter() - start < 30
    prs = load(data)
    assert len(prs.slides) == 8
    for slide in prs.slides:
        assert theme.ILLUSTRATIVE_LABEL in shape_named(slide, "Footer").text_frame.text
    assert views.headline(demo, view)["text"] == title_of(prs.slides[1])
