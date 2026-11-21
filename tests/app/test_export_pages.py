"""Export and Method & limits: rendering in both views and the downloads' payloads."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import openpyxl
import pytest
from pptx import Presentation
from streamlit.testing.v1 import AppTest

from tieout.views import CANNOT_SEE

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGES = ROOT / "app" / "screens"
VIEW_LABELS = {"clean": "Clean team", "masked": "Integration office"}
FILES = "_to_exports"


def _open(page: str, view: str = "clean") -> AppTest:
    at = AppTest.from_file(str(MAIN), default_timeout=120)
    at.session_state["view_mode"] = VIEW_LABELS[view]
    at.run()
    at.switch_page(str(PAGES / f"{page}.py")).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _text(at: AppTest) -> str:
    return "\n".join(str(e.value) for kind in ("markdown", "caption", "info") for e in at.get(kind))


def _build(at: AppTest, key: str) -> AppTest:
    next(b for b in at.button if b.key == key).click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _downloads(at: AppTest) -> dict[str, object]:
    return {e.proto.id: e for e in at.get("download_button")}


@pytest.mark.parametrize("view", ["clean", "masked"])
def test_method_and_limits_renders(view: str) -> None:
    at = _open("method_limits", view)
    text = _text(at)
    for line in CANNOT_SEE:
        assert line in text
    assert "Illustrative — synthetic data" in text
    assert "Naive baseline" in str([f.value.columns.tolist() for f in at.dataframe])
    for word in ("tier A", "Price harmonisation", "Volume consolidation", "Payment terms"):
        assert word in text
    assert "concentration cap" in text


@pytest.mark.parametrize("view", ["clean", "masked"])
def test_export_renders_with_lazy_build_buttons(view: str) -> None:
    at = _open("export", view)
    keys = {b.key for b in at.button}
    assert {"exp_build_workbook", "exp_build_deck", "exp_build_charts"} <= keys
    assert not at.get("download_button") or all(
        d.proto.label.startswith("Download review") for d in at.get("download_button")
    )
    assert "ties" in _text(at) or "match what you see" in _text(at)
    assert "Method & limits" in [p.label for p in at.get("page_link")]
    assert FILES not in at.session_state or not at.session_state[FILES]["files"]


def test_workbook_and_deck_payloads_clean() -> None:
    at = _open("export", "clean")
    _build(at, "exp_build_workbook")
    _build(at, "exp_build_deck")
    files = at.session_state[FILES]["files"]
    workbook, deck = files[("workbook", "clean")], files[("deck", "clean")]
    assert len(workbook) > 100_000 and len(deck) > 50_000
    book = openpyxl.load_workbook(io.BytesIO(workbook))
    assert "Payment_Terms" in book.sheetnames
    assert len(Presentation(io.BytesIO(deck)).slides) == 8
    labels = [d.proto.label for d in at.get("download_button")]
    assert any(label.startswith("Download tieout_workbook.xlsx") for label in labels)
    assert any(label.startswith("Download tieout_deck.pptx") for label in labels)
    # A re-run serves the same bytes without rebuilding.
    at.run()
    assert at.session_state[FILES]["files"][("workbook", "clean")] is workbook


def test_masked_downloads_are_the_masked_variants() -> None:
    at = _open("export", "masked")
    _build(at, "exp_build_workbook")
    _build(at, "exp_build_deck")
    _build(at, "exp_build_charts")
    files = at.session_state[FILES]["files"]
    assert ("workbook", "clean") not in files
    book = openpyxl.load_workbook(io.BytesIO(files[("workbook", "masked")]))
    assert "Payment_Terms" not in book.sheetnames and "Links" not in book.sheetnames
    assert len(Presentation(io.BytesIO(files[("deck", "masked")])).slides) == 8
    with zipfile.ZipFile(io.BytesIO(files[("charts", "masked")])) as archive:
        names = archive.namelist()
        assert "tieout_bridge.png" in names and len(names) == 8
        assert all(archive.read(n)[:8] == b"\x89PNG\r\n\x1a\n" for n in names)
    assert "not available in the integration-office view" in _text(at)


def test_review_decisions_download_follows_the_session() -> None:
    at = _open("export", "clean")
    button = next(d for d in at.get("download_button") if "review_decisions" in d.proto.label)
    assert "0 decisions" in button.proto.label and button.proto.disabled
