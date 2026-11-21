"""Static chart images (PRD 7.3): valid PNGs, clean and masked, with empty-state fallbacks."""

from __future__ import annotations

import struct
from dataclasses import replace

import pandas as pd
import pytest

from tieout.export import charts
from tieout.export.charts import CHART_FUNCTIONS, DPI
from tieout.results import Results

MODES = ("clean", "masked")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == PNG_MAGIC
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize("view", MODES)
@pytest.mark.parametrize("name", sorted(CHART_FUNCTIONS))
def test_chart_is_a_png_at_2x(small_results: Results, name: str, view: str) -> None:
    width, height = png_size(CHART_FUNCTIONS[name](small_results, view))
    assert DPI >= 200
    assert 1400 <= width <= 2400
    assert 800 <= height <= 1400


def test_default_view_is_the_runs_own(small_results: Results) -> None:
    assert charts.bridge_png(small_results) == charts.bridge_png(small_results, "clean")


def test_empty_matrix_and_phasing_give_empty_state(small_results: Results) -> None:
    empty = replace(
        small_results,
        opportunities=small_results.opportunities.iloc[0:0],
        phasing=small_results.phasing.iloc[0:0],
    )
    for view in MODES:
        for fn in (charts.prioritisation_png, charts.phasing_png):
            assert png_size(fn(empty, view)) == (1600, 900)


@pytest.mark.parametrize(
    ("name", "view_function"),
    [
        ("bridge_png", "bridge"),
        ("waterfall_png", "synergy_waterfall"),
        ("tornado_png", "tornado_chart"),
        ("phasing_png", "phasing_by_year"),
        ("prioritisation_png", "prioritisation_matrix"),
    ],
)
def test_empty_view_frame_returns_labelled_image(
    small_results: Results, monkeypatch: pytest.MonkeyPatch, name: str, view_function: str
) -> None:
    monkeypatch.setattr(charts, view_function, lambda *a, **k: pd.DataFrame())
    assert png_size(getattr(charts, name)(small_results, "clean")) == (1600, 900)


def test_scorecard_without_scorecard_is_empty_state(small_results: Results) -> None:
    assert small_results.scorecard is None
    assert png_size(charts.scorecard_png(small_results, "masked")) == (1600, 900)


@pytest.mark.slow
@pytest.mark.parametrize("view", MODES)
def test_demo_charts(view: str) -> None:
    demo = Results.load("data/demo/results")
    for fn in CHART_FUNCTIONS.values():
        assert png_size(fn(demo, view))[0] >= 1400
