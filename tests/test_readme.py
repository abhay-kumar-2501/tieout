"""The README's links and images resolve, and its scorecard table equals the committed scorecard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SCORECARD = json.loads((ROOT / "data/demo/scorecard.json").read_text(encoding="utf-8"))

_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
MAX_SCREENSHOT_BYTES = 400_000

ROWS = {
    "Vendor precision": "vendor_precision",
    "Vendor recall": "vendor_recall",
    "Item precision": "item_precision",
    "Item recall": "item_recall",
    "Planted-savings recall": "planted_savings_recall",
    "False-savings rate": "false_savings_rate",
    "Unit-error catch rate": "unit_error_catch_rate",
}


def _targets() -> list[str]:
    return [m.group(1) for m in _LINK.finditer(README)]


@pytest.mark.parametrize("target", [t for t in _targets() if not re.match(r"[a-z]+:", t)])
def test_relative_links_and_images_resolve(target: str) -> None:
    path, _, fragment = unquote(target).partition("#")
    if not path:  # an in-page anchor
        headings = {
            re.sub(r"[^a-z0-9 -]", "", h.lower()).strip().replace(" ", "-")
            for h in re.findall(r"^#+ (.+)$", README, flags=re.M)
        }
        assert fragment in headings
        return
    assert (ROOT / path).exists(), f"README links to {path}, which is not in the repository"


def test_the_readme_has_the_development_heading_the_landing_page_links_to() -> None:
    assert re.search(r"^## Development$", README, flags=re.M)


def test_screenshots_are_png_and_small() -> None:
    shots = sorted((ROOT / "docs/screenshots").glob("*.png"))
    assert 2 <= len(shots) <= 3
    for shot in shots:
        assert shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert shot.stat().st_size < MAX_SCREENSHOT_BYTES, shot.name


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def test_the_scorecard_table_quotes_the_committed_figures() -> None:
    rows = {}
    for line in README.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0] in ROWS:
            rows[cells[0]] = cells[1:]
    assert set(rows) == set(ROWS)
    for label, key in ROWS.items():
        tool, baseline, target = rows[label]
        assert tool == _pct(SCORECARD["tool"]["held_out"][key]), label
        assert baseline == _pct(SCORECARD["baseline"]["held_out"][key]), label
        bound = SCORECARD["targets"].get(key)
        if bound is None:
            assert target == "none", label
        else:
            words = {">=": "at least", "<=": "at most"}[bound["direction"]]
            assert target == f"{words} {_pct(bound['bound'])}", label


def test_the_headline_figures_match_the_demo_results() -> None:
    results = json.loads((ROOT / "data/demo/results/results.json").read_text(encoding="utf-8"))
    recurring = results["totals"]["recurring"]
    assert f"${recurring['low'] / 1e6:.0f}–{recurring['high'] / 1e6:.0f}M" in README
    assert SCORECARD["held_out_seed"] == 4 and "seed 4" in README
