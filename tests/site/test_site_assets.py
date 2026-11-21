"""The landing page's sample outputs exist and come from the committed demo results (PRD 9.2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import openpyxl
import pytest
from pptx import Presentation

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
ASSETS = SITE / "assets"
RESULTS = ROOT / "data" / "demo" / "results"
SCORECARD = ROOT / "data" / "demo" / "scorecard.json"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "make_site_assets", ROOT / "scripts" / "make_site_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["bridge.png", "tieout_workbook.xlsx", "tieout_deck.pptx"])
def test_the_three_assets_exist(name: str) -> None:
    path = ASSETS / name
    assert path.is_file() and path.stat().st_size > 10_000, name


def test_bridge_image_is_the_real_chart() -> None:
    from PIL import Image

    image = Image.open(ASSETS / "bridge.png")
    assert image.format == "PNG" and image.width >= 1600
    assert (ASSETS / "bridge.png").stat().st_size > 60_000  # the placeholder was 23 KB


def test_workbook_and_deck_open() -> None:
    book = openpyxl.load_workbook(ASSETS / "tieout_workbook.xlsx", read_only=True)
    assert "Summary" in book.sheetnames and "Payment_Terms" in book.sheetnames
    book.close()
    assert len(Presentation(ASSETS / "tieout_deck.pptx").slides) == 8


def test_workbook_stays_a_reasonable_download() -> None:
    assert (ASSETS / "tieout_workbook.xlsx").stat().st_size < 8_000_000


def test_data_js_is_what_the_generator_writes() -> None:
    results_json = json.loads((RESULTS / "results.json").read_text(encoding="utf-8"))
    scorecard = json.loads(SCORECARD.read_text(encoding="utf-8"))
    expected = _generator().data_js_text(results_json, scorecard)
    assert (SITE / "data.js").read_text(encoding="utf-8") == expected


def test_generator_writes_all_files_and_leaves_the_results_alone(tmp_path: Path) -> None:
    before = {p.name: p.stat().st_mtime_ns for p in RESULTS.iterdir()}
    sizes = _generator().write_site_assets(RESULTS, SCORECARD, tmp_path)
    assert set(sizes) == {"bridge.png", "tieout_workbook.xlsx", "tieout_deck.pptx", "data.js"}
    assert all((tmp_path / n).is_file() for n in ("data.js",))
    assert all(
        (tmp_path / "assets" / n).stat().st_size == s for n, s in sizes.items() if n != "data.js"
    )
    assert (tmp_path / "data.js").read_text() == (SITE / "data.js").read_text()
    assert {p.name: p.stat().st_mtime_ns for p in RESULTS.iterdir()} == before
