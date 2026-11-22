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
MANIFEST = ROOT / "data" / "samples.json"
SAMPLE_DIRS = [ASSETS] + sorted(p for p in (ASSETS / "samples").iterdir() if p.is_dir())


def _generator():
    spec = importlib.util.spec_from_file_location(
        "make_site_assets", ROOT / "scripts" / "make_site_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_one_asset_folder_per_sample() -> None:
    ids = [s["id"] for s in json.loads(MANIFEST.read_text(encoding="utf-8"))["samples"]]
    assert [d.name for d in SAMPLE_DIRS[1:]] == sorted(ids[1:])


@pytest.mark.parametrize("folder", SAMPLE_DIRS, ids=lambda p: p.name)
@pytest.mark.parametrize("name", ["bridge.png", "tieout_workbook.xlsx", "tieout_deck.pptx"])
def test_the_three_assets_exist(folder: Path, name: str) -> None:
    path = folder / name
    assert path.is_file() and path.stat().st_size > 10_000, name


@pytest.mark.parametrize("folder", SAMPLE_DIRS, ids=lambda p: p.name)
def test_bridge_image_is_the_real_chart(folder: Path) -> None:
    from PIL import Image

    image = Image.open(folder / "bridge.png")
    assert image.format == "PNG" and image.width >= 1600
    assert (folder / "bridge.png").stat().st_size > 60_000  # the placeholder was 23 KB


@pytest.mark.parametrize("folder", SAMPLE_DIRS, ids=lambda p: p.name)
def test_workbook_and_deck_open(folder: Path) -> None:
    book = openpyxl.load_workbook(folder / "tieout_workbook.xlsx", read_only=True)
    assert "Summary" in book.sheetnames and "Payment_Terms" in book.sheetnames
    book.close()
    assert len(Presentation(folder / "tieout_deck.pptx").slides) == 8


@pytest.mark.parametrize("folder", SAMPLE_DIRS, ids=lambda p: p.name)
def test_workbook_stays_a_reasonable_download(folder: Path) -> None:
    assert (folder / "tieout_workbook.xlsx").stat().st_size < 8_000_000


def test_data_js_is_what_the_generator_writes() -> None:
    generator = _generator()
    scorecard = json.loads(SCORECARD.read_text(encoding="utf-8"))
    expected = generator.data_js_text(generator.read_samples(MANIFEST), scorecard)
    assert (SITE / "data.js").read_text(encoding="utf-8") == expected


def test_generator_writes_all_files_and_leaves_the_results_alone(tmp_path: Path) -> None:
    # The demo and the smallest extra sample keep this test quick; the layout is the same.
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["samples"] = [manifest["samples"][0], manifest["samples"][1]]
    small = tmp_path / "samples.json"
    small.write_text(json.dumps(manifest), encoding="utf-8")
    second = manifest["samples"][1]["id"]
    results = [RESULTS, ROOT / manifest["samples"][1]["results"]]
    before = {p: p.stat().st_mtime_ns for d in results for p in d.iterdir()}
    sizes = _generator().write_site_assets(small, SCORECARD, tmp_path)
    names = ("bridge.png", "tieout_workbook.xlsx", "tieout_deck.pptx")
    assert set(sizes) == (
        {f"assets/{n}" for n in names}
        | {f"assets/samples/{second}/{n}" for n in names}
        | {"data.js"}
    )
    assert all((tmp_path / n).stat().st_size == s for n, s in sizes.items() if n != "data.js")
    # Same chart as the committed one; bytes differ across platforms' font rendering.
    from PIL import Image

    with (
        Image.open(tmp_path / "assets" / "bridge.png") as built,
        Image.open(ASSETS / "bridge.png") as kept,
    ):
        assert (built.format, built.size) == (kept.format, kept.size)
    assert {p: p.stat().st_mtime_ns for d in results for p in d.iterdir()} == before
