"""The type scale and layout rules: nothing in the interface is set below FONT_MIN (PRD 6.11)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

from tieout import theme

APP = Path(__file__).resolve().parents[2] / "app"


def _px(declaration: str) -> list[float]:
    """Every pixel size in a CSS ``font-size`` value; for ``clamp()`` only its minimum counts."""
    clamp = re.match(r"\s*clamp\(\s*([\d.]+)px", declaration)
    if clamp:
        return [float(clamp.group(1))]
    return [float(v) for v in re.findall(r"([\d.]+)px", declaration)]


def test_stylesheet_sets_no_font_size_below_the_minimum() -> None:
    from components.style import stylesheet

    css = stylesheet()
    sizes = [px for value in re.findall(r"font-size:\s*([^;]+);", css) for px in _px(value)]
    assert sizes, "the stylesheet sets font sizes"
    assert min(sizes) >= theme.FONT_MIN


def test_type_tokens_respect_the_minimum() -> None:
    assert theme.BASE_FONT_SIZE >= 16
    assert min(theme.TYPE.values()) >= theme.FONT_MIN
    assert min(theme.CHART_FONT, theme.CHART_TICK, theme.CHART_LABEL) >= theme.FONT_MIN


def _fonts(node: object) -> list[float]:
    """Every ``size`` under a ``font`` / ``tickfont`` / ``textfont`` key of a figure dict."""
    found: list[float] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"font", "tickfont", "textfont"} and isinstance(value, dict):
                size = value.get("size")
                if isinstance(size, int | float):
                    found.append(float(size))
            found += _fonts(value)
    elif isinstance(node, list | tuple):
        for item in node:
            found += _fonts(item)
    return found


def test_chart_defaults_set_no_text_below_the_minimum() -> None:
    from components.plotting import bridge_figure, dot_plot, themed

    frame = pd.DataFrame(
        {
            "label": ["Naive figure", "Unit-of-measure errors", "Defensible run-rate saving"],
            "kind": ["total", "decrease", "total"],
            "amount": [100.0, -40.0, 60.0],
            "bar_base": [0.0, 60.0, 0.0],
            "bar_height": [100.0, 40.0, 60.0],
            "low": [float("nan"), float("nan"), 50.0],
            "high": [float("nan"), float("nan"), 70.0],
            "text": ["$0k", "−$0k", "$0k"],
        }
    )
    points = pd.DataFrame(
        {"price": [1.0, 2.0], "group": ["a", "b"], "company": ["acquirer", "target"],
         "hover": ["x", "y"]}
    )  # fmt: skip
    figures = [
        themed(go.Figure(go.Bar(x=[1], y=[1])), legend=True),
        bridge_figure(frame),
        dot_plot(points, x="price", y="group", color_by="company", colors={}, hover="hover",
                 marker_line=1.5, marker_line_label="Benchmark"),
    ]  # fmt: skip
    for fig in figures:
        sizes = _fonts(fig.to_plotly_json()["layout"]) + _fonts(fig.to_plotly_json()["data"])
        assert sizes and min(sizes) >= theme.FONT_MIN
        assert fig.layout.uniformtext.minsize >= theme.FONT_MIN


def test_no_chart_module_hard_codes_a_small_font() -> None:
    pattern = re.compile(r"(?:font|tickfont|textfont)[^\n]*?[\"']size[\"']\s*:\s*(\d+)")
    for path in (APP / "components").glob("*.py"):
        for size in pattern.findall(path.read_text()):
            assert int(size) >= theme.FONT_MIN, (path.name, size)


def _shaped_chart() -> None:
    import plotly.graph_objects as go
    from components.plotting import show_chart

    show_chart(go.Figure(go.Bar(x=[1], y=[1])), "c", shape="main")


def test_a_shaped_chart_takes_its_role_height_in_a_keyed_container() -> None:
    import json

    at = AppTest.from_function(_shaped_chart).run()
    assert not at.exception
    (chart,) = at.get("plotly_chart")
    assert json.loads(chart.proto.spec)["layout"]["height"] == theme.CHART_HEIGHTS["main"]


def test_an_unknown_chart_shape_is_refused() -> None:
    from components.plotting import show_chart

    with pytest.raises(ValueError, match="unknown chart shape"):
        show_chart(go.Figure(), "c", shape="square")


def test_stylesheet_hides_host_and_developer_controls_from_visitors() -> None:
    from components.style import stylesheet

    css = stylesheet()
    rule = re.search(r"([^{}]+)\{\s*display: none !important;", css)
    assert rule is not None
    for testid in ("stToolbarActions", "stMainMenu", "stAppDeployButton"):
        assert f'[data-testid="{testid}"]' in rule.group(1)
