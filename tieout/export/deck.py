"""The eight-slide deck (PRD 7.2), built in memory with python-pptx.

Every number and every chart series comes from the view functions with the
view mode passed through; nothing is recomputed here. Slides use only the blank
layout and add their own shapes, so no empty placeholder remains. Charts are
native PowerPoint charts (bridge, waterfall, matrix, phasing and spend by
company), so a consultant can restyle them; the Pareto combines bars and a line
and is a matplotlib image. Text boxes are sized deliberately: font sizes shrink
until an estimate of the wrapped text fits the box, and no two shapes overlap.
"""

from __future__ import annotations

import io
import math
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd
from lxml import etree
from pptx import Presentation
from pptx.chart.data import BubbleChartData, CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_TICK_LABEL_POSITION,
)
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.slide import Slide
from pptx.util import Inches, Pt

from tieout import theme
from tieout.export.charts import pareto_png
from tieout.views import (
    CANNOT_SEE,
    MASKED,
    Unavailable,
    bridge,
    concentration,
    confidence_strip,
    data_quality_summary,
    headline,
    matching_counts,
    money,
    money_range,
    overview_figures,
    percent,
    phasing_by_year,
    prioritisation_matrix,
    review_progress,
    scorecard_table,
    spend_pareto,
    synergy_waterfall,
    thousands,
)
from tieout.views.common import resolve_view

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = ["SLIDE_COUNT", "build_deck"]

SLIDE_COUNT = 8
SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.6
CONTENT_W = SLIDE_W - 2 * MARGIN
BODY_TOP, BODY_BOTTOM = 1.5, 6.45
BODY_H = BODY_BOTTOM - BODY_TOP
TITLE_FONT, BODY_FONT = theme.EXPORT_FONT_TITLE, theme.EXPORT_FONT_BODY
TITLE_MAX_CHARS = 120
WAVE_COLOURS = (theme.INK, theme.MUTED, theme.CONTROL)
VIEW_NAMES = {"clean": "Clean-team view", "masked": "Integration-office view"}


def _rgb(hex_colour: str) -> RGBColor:
    return RGBColor.from_string(hex_colour.lstrip("#"))


# ---------------------------------------------------------------- text fitting


@dataclass(frozen=True)
class Para:
    """One paragraph: its text, nominal size in points and look."""

    text: str
    size: float = 14.0
    bold: bool = False
    colour: str = theme.INK
    font: str = BODY_FONT
    after: float = 0.0  # space after, points
    align: str = "left"


def _lines(text: str, width_pt: float, size: float, bold: bool) -> int:
    per_line = max(1, int(width_pt / (size * (0.58 if bold else 0.53))))
    return sum(max(1, len(textwrap.wrap(part, per_line) or [""])) for part in text.split("\n"))


def _height_pt(paras: Sequence[Para], width_in: float, scale: float) -> float:
    total = 0.0
    for p in paras:
        size = p.size * scale
        total += _lines(p.text, width_in * 72, size, p.bold) * size * 1.2 + p.after * scale
    return total


def _fit_scale(paras: Sequence[Para], width_in: float, height_in: float) -> float:
    for step in range(0, 13):
        scale = 1.0 - 0.04 * step
        if _height_pt(paras, width_in, scale) <= height_in * 72:
            return scale
    return 0.52


def _fill(paragraphs: Any, paras: Sequence[Para], scale: float) -> None:
    for i, p in enumerate(paras):
        para = paragraphs.add_paragraph() if i else paragraphs.paragraphs[0]
        run = para.add_run()
        run.text = p.text
        run.font.size = Pt(max(10.0, round(p.size * scale, 1)))
        run.font.bold = p.bold
        run.font.name = p.font
        run.font.color.rgb = _rgb(p.colour)
        para.space_after = Pt(p.after * scale)
        para.alignment = {"left": PP_ALIGN.LEFT, "right": PP_ALIGN.RIGHT}.get(
            p.align, PP_ALIGN.CENTER
        )


def _text(
    slide: Slide,
    box: tuple[float, float, float, float],
    paras: Sequence[Para],
    name: str,
    anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
) -> Any:
    x, y, w, h = box
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    shape.name = name
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = anchor
    _fill(frame, paras, _fit_scale(paras, w, h))
    return shape


def _card(
    slide: Slide,
    box: tuple[float, float, float, float],
    paras: Sequence[Para],
    name: str,
    fill: str = theme.SURFACE,
    border: str = theme.BORDER,
) -> Any:
    x, y, w, h = box
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.name = name
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill)
    shape.line.color.rgb = _rgb(border)
    shape.line.width = Pt(1)
    shape.shadow.inherit = False
    frame = shape.text_frame
    frame.word_wrap = True
    pad = 0.14
    frame.margin_left = frame.margin_right = Inches(pad)
    frame.margin_top = frame.margin_bottom = Inches(0.1)
    frame.vertical_anchor = MSO_ANCHOR.TOP
    _fill(frame, paras, _fit_scale(paras, w - 2 * pad, h - 0.2))
    return shape


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------- tables


def _table(
    slide: Slide,
    origin: tuple[float, float],
    widths: Sequence[float],
    rows: Sequence[Sequence[str]],
    row_h: float,
    size: float,
    name: str,
    right: Sequence[int] = (),
    header: bool = True,
) -> Any:
    x, y = origin
    shape = slide.shapes.add_table(
        len(rows), len(widths), Inches(x), Inches(y), Inches(sum(widths)), Inches(row_h * len(rows))
    )
    shape.name = name
    table = shape.table
    table.first_row = False
    table.horz_banding = False
    for c, width in enumerate(widths):
        table.columns[c].width = Inches(width)
    for r, values in enumerate(rows):
        table.rows[r].height = Inches(row_h)
        is_head = header and r == 0
        for c, value in enumerate(values):
            cell = table.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(theme.INK if is_head else theme.SURFACE)
            frame = cell.text_frame
            frame.word_wrap = True
            para = frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if c in right else PP_ALIGN.LEFT
            run = para.add_run()
            run.text = value
            run.font.size = Pt(size)
            run.font.name = BODY_FONT
            run.font.bold = is_head
            run.font.color.rgb = _rgb(theme.SURFACE if is_head else theme.INK)
    return shape


# ---------------------------------------------------------------- native charts


def _style_chart(chart: Any, legend: bool = False) -> None:
    chart.font.name = BODY_FONT
    chart.font.size = Pt(11)
    chart.font.color.rgb = _rgb(theme.MUTED)
    chart.has_title = False
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(11)


def _style_axis(
    axis: Any,
    number_format: str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    title: str | None = None,
    gridlines: bool = True,
) -> None:
    axis.has_major_gridlines = gridlines
    if gridlines:
        axis.major_gridlines.format.line.color.rgb = _rgb(theme.BORDER)
        axis.major_gridlines.format.line.width = Pt(0.75)
    axis.format.line.color.rgb = _rgb(theme.CONTROL)
    axis.tick_labels.font.size = Pt(11)
    axis.tick_labels.font.color.rgb = _rgb(theme.MUTED)
    if number_format:
        axis.tick_labels.number_format = number_format
        axis.tick_labels.number_format_is_linked = False
    if minimum is not None:
        axis.minimum_scale = minimum
    if maximum is not None:
        axis.maximum_scale = maximum
    if title:
        axis.has_title = True
        axis.axis_title.text_frame.text = title
        run = axis.axis_title.text_frame.paragraphs[0].runs[0]
        run.font.size = Pt(11)
        run.font.bold = False
        run.font.name = BODY_FONT
        run.font.color.rgb = _rgb(theme.MUTED)


def _hide_legend_entries(chart: Any, indices: Sequence[int]) -> None:
    legend = chart._chartSpace.chart.find(qn("c:legend"))
    position = legend.find(qn("c:legendPos"))
    for idx in sorted(indices, reverse=True):
        entry = etree.SubElement(legend, qn("c:legendEntry"))
        etree.SubElement(entry, qn("c:idx")).set("val", str(idx))
        etree.SubElement(entry, qn("c:delete")).set("val", "1")
        legend.remove(entry)
        position.addnext(entry)


def _no_fill(series: Any) -> None:
    series.format.fill.background()
    series.format.line.fill.background()


def _solid(target: Any, colour: str) -> None:
    fmt = target if hasattr(target, "fill") else target.format
    fmt.fill.solid()
    fmt.fill.fore_color.rgb = _rgb(colour)
    fmt.line.fill.background()


def _label(point: Any, text: str, colour: str = theme.INK, size: float = 11) -> None:
    label = point.data_label
    frame = label.text_frame
    frame.text = text
    for para in frame.paragraphs:
        for run in para.runs:
            run.font.size = Pt(size)
            run.font.bold = True
            run.font.name = BODY_FONT
            run.font.color.rgb = _rgb(colour)


def _column_chart(
    slide: Slide,
    box: tuple[float, float, float, float],
    categories: Sequence[str],
    series: Sequence[tuple[str, Sequence[float]]],
    name: str,
    legend: bool = False,
) -> Any:
    data = CategoryChartData()
    data.categories = list(categories)
    for series_name, values in series:
        data.add_series(series_name, [float(v) for v in values])
    x, y, w, h = box
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_STACKED, Inches(x), Inches(y), Inches(w), Inches(h), data
    )
    frame.name = name
    chart = frame.chart
    _style_chart(chart, legend)
    plot = chart.plots[0]
    plot.gap_width = 45
    plot.overlap = 100
    return chart


def _floating_chart(
    slide: Slide,
    box: tuple[float, float, float, float],
    frame: pd.DataFrame,
    name: str,
    bottom: float = 0.0,
    axis_title: str | None = None,
) -> Any:
    """Stacked bars with an invisible base and a label carrier on top (PRD 7.2).

    ``frame`` is a view's bridge or waterfall frame. The labels are the view's
    own ``text`` (and the range, where the view gives one).
    """
    top = float((frame["bar_base"] + frame["bar_height"]).max())
    span = top - bottom
    carrier = span * 0.17
    categories = [str(v) for v in frame["label"]]
    chart = _column_chart(
        slide,
        box,
        categories,
        [
            ("Base", frame["bar_base"]),
            ("Amount", frame["bar_height"]),
            ("Label", [carrier] * len(frame)),
        ],
        name,
    )
    base, amount, label = chart.plots[0].series
    _no_fill(base)
    _no_fill(label)
    for i, row in enumerate(frame.itertuples(index=False)):
        point = amount.points[i]
        _solid(
            point.format,
            theme.INK if i == 0 else theme.CONTROL if row.kind == "decrease" else theme.TEAL,
        )
        text = str(row.text)
        if not math.isnan(row.low):
            text += "\nrange " + money_range(float(row.low), float(row.high))
        _label(label.points[i], text)
        label.points[i].data_label.position = XL_LABEL_POSITION.INSIDE_BASE
    _style_axis(
        chart.value_axis,
        '"$"#,##0,,"M"',
        minimum=bottom,
        maximum=top + carrier * 1.05,
        title=axis_title,
    )
    _style_axis(chart.category_axis, gridlines=False)
    chart.category_axis.tick_labels.font.size = Pt(10)
    return chart


def _nice_floor(value: float, step: float) -> float:
    return math.floor(value / step) * step


def _phasing_chart(
    slide: Slide, box: tuple[float, float, float, float], years: pd.DataFrame
) -> Any:
    years = years[years["year"] != "Total"]
    peak = float(years["savings"].max()) or 1.0
    carrier = peak * 0.14
    chart = _column_chart(
        slide,
        box,
        [f"Year {int(y)}" for y in years["year"]],
        [
            ("Wave 1", years["wave_1"]),
            ("Wave 2", years["wave_2"]),
            ("Wave 3", years["wave_3"]),
            ("One-time cost", years["cost"]),
            ("Total", [carrier] * len(years)),
            ("Cost label", [-carrier] * len(years)),
        ],
        "Phasing chart",
        legend=True,
    )
    series = list(chart.plots[0].series)
    for s, colour in zip(series[:3], WAVE_COLOURS, strict=True):
        _solid(s, colour)
    _solid(series[3], theme.RED)
    _no_fill(series[4])
    _no_fill(series[5])
    for i, row in enumerate(years.itertuples(index=False)):
        _label(series[4].points[i], thousands(float(row.savings)))
        series[4].points[i].data_label.position = XL_LABEL_POSITION.INSIDE_BASE
        _label(series[5].points[i], thousands(float(row.cost)), colour=theme.RED)
        series[5].points[i].data_label.position = XL_LABEL_POSITION.INSIDE_BASE
    _style_axis(
        chart.value_axis,
        '"$"#,##0.0,,"M"',
        minimum=-peak * 0.5,
        maximum=peak * 1.3,
        title="Realised in the year",
    )
    _style_axis(chart.category_axis, gridlines=False)
    chart.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    _hide_legend_entries(chart, [4, 5])
    return chart


def _matrix_chart(
    slide: Slide, box: tuple[float, float, float, float], matrix: pd.DataFrame
) -> Any:
    data = BubbleChartData()
    waves = {w: data.add_series(f"Wave {w}") for w in (1, 2, 3)}
    placed: list[tuple[int, int, int]] = []  # (wave, point index within series, rank)
    counts = {1: 0, 2: 0, 3: 0}
    for rank, row in enumerate(matrix.itertuples(index=False), start=1):
        wave = int(row.wave)
        waves[wave].add_data_point(float(row.complexity), float(row.base), float(row.spend))
        if row.show_label:
            placed.append((wave, counts[wave], rank))
        counts[wave] += 1
    x, y, w, h = box
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.BUBBLE, Inches(x), Inches(y), Inches(w), Inches(h), data
    )
    frame.name = "Prioritisation matrix"
    chart = frame.chart
    _style_chart(chart, legend=True)
    chart.plots[0].bubble_scale = 35
    series = list(chart.plots[0].series)
    for s, colour in zip(series, WAVE_COLOURS, strict=True):
        _solid(s, colour)
        s.format.line.color.rgb = _rgb(theme.PAPER)
    by_wave = dict(zip((1, 2, 3), series, strict=True))
    for wave, index, rank in placed:
        point = by_wave[wave].points[index]
        _label(point, str(rank), colour=theme.INK, size=11)
        point.data_label.position = XL_LABEL_POSITION.ABOVE
    _style_axis(
        chart.category_axis,
        "0.0",
        minimum=0.5,
        maximum=5.0,
        title="Complexity (1 easy, 5 hard)",
        gridlines=False,
    )
    _style_axis(chart.value_axis, '"$"#,##0,"k"', minimum=0, title="Base-case saving a year")
    return chart


def _pictures(slide: Slide, png: bytes, box: tuple[float, float, float, float], name: str) -> Any:
    x, y, w, _ = box
    shape = slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), width=Inches(w))
    shape.name = name
    return shape


# ---------------------------------------------------------------- slide frame


@dataclass(frozen=True)
class _Context:
    results: Results
    view: str
    demo: bool

    @property
    def masked(self) -> bool:
        return self.view == MASKED


def _frame(prs: Any, ctx: _Context, number: int, title: str, source: str, notes: str) -> Slide:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title = _clip(title, TITLE_MAX_CHARS)
    _text(
        slide,
        (MARGIN, 0.35, CONTENT_W, 1.0),
        [Para(title, 26, True, theme.INK, TITLE_FONT)],
        "Title",
    )
    _text(
        slide,
        (MARGIN, 6.55, CONTENT_W, 0.4),
        [Para(source, 11, False, theme.MUTED)],
        "Source",
    )
    footer = f"Tie-Out · {VIEW_NAMES[ctx.view]}"
    if ctx.demo:
        footer += f" · {theme.ILLUSTRATIVE_LABEL}"
    _text(
        slide,
        (MARGIN, 7.02, 10.5, 0.3),
        [Para(footer, 10.5, False, theme.MUTED)],
        "Footer",
    )
    _text(
        slide,
        (SLIDE_W - MARGIN - 1.0, 7.02, 1.0, 0.3),
        [Para(str(number), 10.5, False, theme.MUTED, align="right")],
        "Page number",
    )
    slide.notes_slide.notes_text_frame.text = notes
    return slide


def _source(ctx: _Context, tabs: str) -> str:
    return f"Source: Tie-Out results, {VIEW_NAMES[ctx.view].lower()}. Workbook: {tabs}."


# ---------------------------------------------------------------- slides


def _slide_title_scope(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    head = headline(r, v)
    quality = data_quality_summary(r, v)
    spend = quality["in_scope_spend"]
    if head["high"] > 0:
        title = f"Procurement synergy sizing: {head['range_text']} of run-rate savings"
    else:
        title = "Procurement synergy sizing: no run-rate saving found"
    period = quality["period"]
    if period:
        span = f"{period['start']} to {period['end']} ({period['months']} months)"
    else:
        span = "Period not stated"
    slide = _frame(
        prs,
        ctx,
        1,
        title,
        _source(ctx, "README, Summary"),
        "Scope of the run: companies, period, in-scope spend and the view mode.",
    )
    _text(
        slide,
        (MARGIN, 1.5, CONTENT_W, 0.5),
        [
            Para(
                "A tie-out of the acquirer's and the target's purchasing, from raw purchase lines",
                18,
                False,
                theme.MUTED,
            )
        ],
        "Subtitle",
    )
    if ctx.masked:
        view_text = (
            "Integration-office view: vendors shown as codes, no unit prices, results by "
            "category. A presentation mode, not a security control."
        )
    else:
        view_text = "Clean-team view: full detail, including vendor names and unit prices."
    rows = [
        ["Scope", "Detail"],
        ["Companies", "Acquirer and target"],
        ["Period", span],
        [
            "In-scope spend",
            f"{money(spend['total'])} combined: acquirer {money(spend['acquirer'])}, "
            f"target {money(spend['target'])}",
        ],
        ["View", view_text],
        ["Data", theme.ILLUSTRATIVE_LABEL if ctx.demo else "Uploaded data"],
    ]
    _table(slide, (MARGIN, 2.3), [2.6, CONTENT_W - 2.6], rows, 0.62, 15, "Scope table")


def _slide_summary(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    head = headline(r, v)
    frame = bridge(r, v)
    naive, lever1, lever2 = (float(frame["amount"].iloc[i]) for i in (0, -3, -2))
    strip = confidence_strip(r, v)
    points = []
    if lever1 > 0 and lever2 > 0:
        points.append(
            f"Price harmonisation contributes {money(lever1)} a year and volume consolidation "
            f"{money(lever2)}, in the base case. The range runs from the low to the high "
            "capture assumptions."
        )
    elif lever1 > 0 or lever2 > 0:
        points.append(f"The base case is {money(max(lever1, lever2))} a year from one lever.")
    if naive > 0 and lever1 > 0:
        points.append(
            f"Seven checks reduce the naive price gap of {money(naive)} to {money(lever1)} "
            "of price harmonisation: unit errors, unverified matches and spot prices "
            "come out first."
        )
    points.append(strip["text"])
    slide = _frame(
        prs,
        ctx,
        2,
        head["text"],
        _source(ctx, "Summary, Bridge"),
        "Run-rate saving is recurring. The cash release is a one-off and the one-time cost "
        "is paid once; neither is added to the run-rate figure.",
    )
    paras = [Para(p, 17, False, theme.INK, after=14) for p in points]
    _text(slide, (MARGIN, BODY_TOP, 6.9, BODY_H), paras, "Supporting points")
    gap, card_h = 0.15, (BODY_H - 0.3) / 3
    for i, figure in enumerate(overview_figures(r, v)):
        value = figure["text"] if figure["available"] else "Not available"
        explanation = figure["explanation"]
        fill = theme.TEAL_TINT if figure["kind"] == "recurring" else theme.SURFACE
        _card(
            slide,
            (7.9, BODY_TOP + i * (card_h + gap), SLIDE_W - MARGIN - 7.9, card_h),
            [
                Para(figure["label"], 13, True, theme.MUTED),
                Para(value, 28, True, theme.INK, TITLE_FONT, after=2),
                Para(explanation, 11.5, False, theme.INK),
            ],
            f"Figure: {figure['label']}",
            fill=fill,
        )


def _slide_baseline(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    data = spend_pareto(r, v)
    quality = data_quality_summary(r, v)
    counts = matching_counts(r, v)
    spend = quality["in_scope_spend"]
    reach = data["vendors_to_share"]
    title = (
        f"{data['vendor_records']:,} vendor records are {data['parent_vendors']:,} parent "
        f"vendors; {reach['after']:,} of them hold {data['share']:.0%} of spend"
    )
    tabs = "Spend_Cube" if ctx.masked else "Spend_Cube, Vendor_Map"
    slide = _frame(
        prs,
        ctx,
        3,
        title,
        _source(ctx, tabs),
        "Combined in-scope spend by company, and how fragmented the vendor base is before "
        "and after matching vendor records to parent companies.",
    )
    chart_data = CategoryChartData()
    chart_data.categories = ["Acquirer", "Target"]
    chart_data.add_series("In-scope spend", [spend["acquirer"], spend["target"]])
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(MARGIN),
        Inches(BODY_TOP),
        Inches(4.1),
        Inches(3.3),
        chart_data,
    )
    frame.name = "Spend by company"
    chart = frame.chart
    _style_chart(chart)
    chart.plots[0].gap_width = 60
    series = chart.plots[0].series[0]
    for i, (key, colour) in enumerate((("acquirer", theme.ACQUIRER), ("target", theme.TARGET))):
        _solid(series.points[i].format, colour)
        _label(series.points[i], money(spend[key]))
        series.points[i].data_label.position = XL_LABEL_POSITION.OUTSIDE_END
    _style_axis(
        chart.value_axis,
        '"$"#,##0,,"M"',
        minimum=0,
        maximum=spend["acquirer"] * 1.2,
        title="In-scope spend",
    )
    _style_axis(chart.category_axis, gridlines=False)
    _text(
        slide,
        (MARGIN, 4.95, 4.1, 1.5),
        [
            Para(f"{money(spend['total'])} in scope", 16, True),
            Para(quality["not_item_addressable"]["text"], 12.5, False, theme.INK),
        ],
        "Spend note",
    )
    picture_w = 7.3
    _pictures(slide, pareto_png(r, v), (5.0, BODY_TOP, picture_w, 0), "Pareto image")
    _text(
        slide,
        (5.0, 5.2, picture_w, 1.25),
        [
            Para(
                f"{reach['before']:,} vendor records reach {data['share']:.0%} of spend; after "
                f"matching, {reach['after']:,} parent vendors do.",
                14,
                True,
                after=4,
            ),
            Para(counts["vendors"]["text"], 12.5),
        ],
        "Pareto caption",
    )


def _slide_bridge(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    frame = bridge(r, v)
    naive, lever1, lever2 = (float(frame["amount"].iloc[i]) for i in (0, -3, -2))
    if naive > lever1 > 0:
        title = (
            f"Seven checks cut the naive {money(naive)} price gap to {money(lever1)}; "
            f"volume consolidation adds {money(lever2)}"
        )
    elif lever1 > 0:
        title = (
            f"The naive figure of {money(naive)} holds up: {money(lever1)} of price harmonisation"
        )
    else:
        title = f"None of the naive {money(naive)} price gap survives the seven checks"
    slide = _frame(
        prs,
        ctx,
        4,
        title,
        _source(ctx, "Bridge, Bridge_Detail" if not ctx.masked else "Bridge, Bridge_By_Category"),
        "Each grey bar is the part of the naive gap that one check removes. Teal bars are "
        "defensible saving, with the low to high range on the last bar.",
    )
    _floating_chart(
        slide,
        (MARGIN, BODY_TOP, CONTENT_W, BODY_H),
        frame,
        "Bridge chart",
        axis_title="Annual price gap (removals in grey)",
    )


def _slide_levers(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    head = headline(r, v)
    figures = {f["id"]: f for f in overview_figures(r, v)}
    waterfall = synergy_waterfall(r, v)
    cash, cost = figures["cash"], figures["cost"]
    title = f"Price harmonisation and volume consolidation save {head['range_text']} a year"
    if cash["available"] and cash["base"] > 0:
        title += f"; payment terms release {cash['text']} once"
    slide = _frame(
        prs,
        ctx,
        5,
        title,
        _source(ctx, "Summary, Opportunities")
        + " The vertical axis starts above zero so that the levers are visible.",
        "Recurring savings only. The cash release is working capital released once by "
        "harmonising payment terms; it is not a saving.",
    )
    low = float(waterfall[["level", "low"]].min().min())
    saved = float(waterfall["bar_height"].iloc[1:3].sum()) or 1.0
    bottom = max(0.0, _nice_floor(low - 1.5 * saved, 5e6 if low > 5e7 else 1e6))
    _floating_chart(
        slide,
        (MARGIN, BODY_TOP, 7.9, BODY_H),
        waterfall,
        "Waterfall chart",
        bottom=bottom,
        axis_title=f"Annual spend (axis starts at {money(bottom)})",
    )
    x, w = 8.8, SLIDE_W - MARGIN - 8.8
    card_h = (BODY_H - 0.15) / 2
    cash_value = cash["text"] if cash["available"] else "Not available"
    _card(
        slide,
        (x, BODY_TOP, w, card_h),
        [
            Para("One-time cash release", 13, True, theme.MUTED),
            Para(cash_value, 28, True, theme.INK, TITLE_FONT, after=2),
            Para(cash["explanation"], 11.5),
        ],
        "Callout: cash release",
        fill=theme.SURFACE,
    )
    _card(
        slide,
        (x, BODY_TOP + card_h + 0.15, w, card_h),
        [
            Para("One-time cost", 13, True, theme.MUTED),
            Para(cost["text"], 28, True, theme.RED, TITLE_FONT, after=2),
            Para(cost["explanation"], 11.5),
        ],
        "Callout: one-time cost",
        fill=theme.RED_TINT,
        border=theme.RED,
    )


def _slide_priorities(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    matrix = prioritisation_matrix(r, v)
    years = phasing_by_year(r, v)
    year3 = float(years.loc[years["year"] == 3, "savings"].iloc[0])
    net = float(years.loc[years["year"] == "Total", "net_base"].iloc[0])
    if year3 > 0:
        title = (
            f"Realised savings ramp to {money(year3)} a year by year 3; "
            f"net three-year value is {money(net)}"
        )
    else:
        title = "No saving is realised within the three-year planning horizon"
    top = matrix.head(10)
    notes = "Top negotiation targets by base-case saving:\n" + "\n".join(
        f"{i}. {row.label}: {thousands(float(row.base))} a year (wave {int(row.wave)})"
        for i, row in enumerate(top.itertuples(index=False), start=1)
    )
    tabs = "Opportunities, Phasing"
    slide = _frame(prs, ctx, 6, title, _source(ctx, tabs), notes)
    left_w = 6.2
    _matrix_chart(slide, (MARGIN, BODY_TOP, left_w, BODY_H), matrix)
    x = MARGIN + left_w + 0.3
    w = SLIDE_W - MARGIN - x
    _phasing_chart(slide, (x, BODY_TOP, w, 2.6), years)
    rows = [["#", "Top five negotiation targets", "Saving", "Wave"]]
    for i, row in enumerate(top.head(5).itertuples(index=False), start=1):
        rows.append(
            [str(i), _clip(str(row.label), 36), thousands(float(row.base)), str(int(row.wave))]
        )
    if len(rows) > 1:
        _table(
            slide,
            (x, 4.3),
            [0.4, w - 0.4 - 0.95 - 0.7, 0.95, 0.7],
            rows,
            0.36,
            12,
            "Top five table",
            right=(2, 3),
        )


def _target(text: str) -> str:
    operator, _, bound = str(text).partition(" ")
    sign = {">=": "≥", "<=": "≤"}.get(operator, operator)
    return f"{sign} {percent(float(bound))}" if bound else str(text)


def _slide_risks(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    risk = concentration(r, v)
    categories = risk["categories"]
    forgone = float(categories["savings_forgone"].sum())
    limited = int(categories["cap_limits"].sum())
    if forgone > 0:
        title = (
            f"Concentration caps give up {money(forgone)} a year of consolidation savings "
            f"in {limited} categories"
        )
    else:
        title = "No concentration cap limits consolidation; eight blind spots are listed"
    slide = _frame(
        prs,
        ctx,
        7,
        title,
        _source(ctx, "Risk, Assumptions, README"),
        "Savings forgone is the consolidation saving given up to keep each category's largest "
        "vendor under its concentration cap. The right-hand list is fixed text.",
    )
    left_w = 6.4
    rows = [["Category", "Cap", "Concentration index", "Forgone"]]
    for row in categories.head(5).itertuples(index=False):
        cap = "" if pd.isna(row.cap) else percent(float(row.cap))
        rows.append(
            [
                _clip(str(row.category), 30),
                cap,
                f"{row.hhi_before:,.0f} → {row.hhi_after:,.0f}",
                thousands(float(row.savings_forgone)),
            ]
        )
    _text(
        slide,
        (MARGIN, BODY_TOP, left_w, 0.3),
        [Para("Most savings given up for resilience", 14, True)],
        "Concentration heading",
    )
    _table(
        slide,
        (MARGIN, BODY_TOP + 0.4),
        [2.9, 0.7, 1.8, 1.0],
        rows,
        0.37,
        12,
        "Concentration table",
        right=(1, 2, 3),
    )
    a = r.assumptions
    assumptions = [
        "Capture, base case: "
        f"{percent(a['lever1']['same_vendor']['base'])} price gap at the same vendor, "
        f"{percent(a['lever1']['switch']['base'])} when switching, "
        f"{percent(a['lever2']['capture']['base'])} of volume-consolidation discount.",
        "Concentration caps: critical "
        f"{percent(a['caps']['critical'])}, standard {percent(a['caps']['standard'])}, "
        f"other {percent(a['caps']['non_critical'])}.",
        f"Planning horizon {a['planning_horizon_months']} months; cost of capital "
        f"{percent(a['cost_of_capital'])}.",
    ]
    _text(
        slide,
        (MARGIN, 4.55, left_w, 0.3),
        [Para("Key assumptions", 14, True)],
        "Assumptions heading",
    )
    _text(
        slide,
        (MARGIN, 4.9, left_w, 1.55),
        [Para(t, 12, False, after=4) for t in assumptions],
        "Assumptions",
    )
    x = MARGIN + left_w + 0.35
    _card(
        slide,
        (x, BODY_TOP, SLIDE_W - MARGIN - x, BODY_H),
        [Para("What this analysis cannot see", 14, True, after=6)]
        + [Para("•  " + item, 12, False, after=3) for item in CANNOT_SEE],
        "Cannot see",
        fill=theme.AMBER_TINT,
        border=theme.AMBER,
    )


def _slide_audit(prs: Any, ctx: _Context) -> None:
    r, v = ctx.results, ctx.view
    counts = matching_counts(r, v)
    quality = data_quality_summary(r, v)
    card = scorecard_table(r, v)
    vendors, items = counts["vendors"], counts["items"]
    if isinstance(card, Unavailable):
        title = (
            f"{vendors['records']:,} vendor records resolve to {vendors['legal_entities']:,} "
            f"legal entities; {items['records']:,} items to {items['canonical_items']:,}"
        )
    else:
        graded = card[card["passed"].notna()]
        met = int(graded["passed"].astype(bool).sum())
        title = (
            f"{vendors['records']:,} vendor records resolve to {vendors['legal_entities']:,} "
            f"legal entities; {met} of {len(graded)} accuracy targets met"
        )
    progress = review_progress(r, v)
    review = (
        "Review decisions are not shown in the integration-office view."
        if isinstance(progress, Unavailable)
        else f"Review decisions: {progress['decided']:,} made, {progress['pending']:,} pending."
    )
    tabs = (
        "Data_Quality, Scorecard"
        if ctx.masked
        else "Data_Quality, Vendor_Map, Item_Map, Review_Log, Scorecard"
    )
    slide = _frame(
        prs,
        ctx,
        8,
        title,
        _source(ctx, tabs),
        "Volumes processed, how matches were made and how accurate the matching is on the "
        "held-out demo seed. The scorecard exists only for the demo data.",
    )
    rows = quality["rows"]
    tiers_v, tiers_i = vendors["by_tier"], items["by_tier"]
    left_w = 5.7
    _text(
        slide,
        (MARGIN, BODY_TOP, left_w, BODY_H),
        [
            Para("What was processed", 14, True, after=4),
            Para(
                f"{sum(rows.values()):,} purchase lines: "
                + ", ".join(f"{k} {n:,}" for k, n in rows.items())
                + ".",
                13,
                after=8,
            ),
            Para(vendors["text"], 13, after=8),
            Para(items["text"], 13, after=12),
            Para("Match tiers", 14, True, after=4),
            Para(
                f"Vendors: tier A {tiers_v.get('A', 0):,}, tier B {tiers_v.get('B', 0):,}, "
                f"unmatched {tiers_v.get('none', 0):,}.",
                13,
                after=6,
            ),
            Para(
                f"Items: tier A {tiers_i.get('A', 0):,}, tier B {tiers_i.get('B', 0):,}, "
                f"unmatched {tiers_i.get('none', 0):,}.",
                13,
                after=12,
            ),
            Para(review, 13),
        ],
        "Audit figures",
    )
    x = MARGIN + left_w + 0.4
    w = SLIDE_W - MARGIN - x
    if isinstance(card, Unavailable):
        _card(
            slide,
            (x, BODY_TOP, w, 1.4),
            [
                Para("Accuracy scorecard omitted", 14, True, after=4),
                Para(
                    card.message
                    or "A scorecard needs known matches, which uploaded data does not have.",
                    12.5,
                ),
            ],
            "Scorecard note",
        )
        return
    table = [["Metric (held-out seed)", "Tie-Out", "Baseline", "Target"]]
    for row in card.itertuples(index=False):
        target = _target(row.target) if row.target else "—"
        if row.target:
            target += " ✓" if row.passed else " ✗"
        table.append([row.label, percent(float(row.tool)), percent(float(row.baseline)), target])
    _table(
        slide,
        (x, BODY_TOP),
        [2.45, 0.95, 0.95, w - 4.35],
        table,
        0.42,
        12,
        "Scorecard table",
        right=(1, 2),
    )


# ---------------------------------------------------------------- build


def build_deck(results: Results, view: str | None = None) -> bytes:
    """The eight-slide 16:9 deck of PRD 7.2 as ``.pptx`` bytes.

    ``view`` is ``"clean"`` or ``"masked"``; omitted, the run's own mode.
    """
    mode = resolve_view(results, view)
    ctx = _Context(results, mode, str(results.meta.get("scenario", "")) == "demo")
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SLIDE_W), Inches(SLIDE_H)
    for build in (
        _slide_title_scope,
        _slide_summary,
        _slide_baseline,
        _slide_bridge,
        _slide_levers,
        _slide_priorities,
        _slide_risks,
        _slide_audit,
    ):
        build(prs, ctx)
    prs.core_properties.title = "Tie-Out: procurement synergy sizing"
    prs.core_properties.author = "Tie-Out"
    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
