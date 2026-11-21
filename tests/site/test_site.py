"""Checks on the static landing page in site/ (PRD 2.2, 9.4)."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
SAMPLE_DOWNLOADS = {"assets/tieout_workbook.xlsx", "assets/tieout_deck.pptx"}


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, str, str]] = []  # (tag, attr, value)
        self.comments: list[str] = []
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for name, value in attrs:
            if name in ("src", "href") and value is not None:
                self.refs.append((tag, name, value))

    def handle_comment(self, data):
        self.comments.append(data)


def _parse() -> _Collector:
    p = _Collector()
    p.feed((SITE / "index.html").read_text(encoding="utf-8"))
    p.close()
    return p


def _js_object(path: Path, name: str) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"const {name} = (\{{.*\}});", text, re.S)
    assert m, f"{name} not found in {path.name}"
    return json.loads(m.group(1))


def test_html_parses_and_has_basics():
    p = _parse()
    assert {"title", "main", "h1", "img"} <= set(p.tags)
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'name="description"' in html
    assert 'rel="icon"' in html


def test_local_references_resolve():
    for tag, attr, value in _parse().refs:
        if re.match(r"^(https?:|mailto:|data:|#)", value):
            continue
        rel = value.split("#")[0].split("?")[0]
        if not rel or rel in SAMPLE_DOWNLOADS:
            continue
        assert (SITE / rel).is_file(), f"<{tag} {attr}={value}> does not resolve"


def test_no_external_resource_loads():
    for tag, attr, value in _parse().refs:
        if re.match(r"^https?://", value):
            assert tag == "a", f"<{tag} {attr}={value}> loads an external resource"
    for name in ("styles.css", "main.js", "config.js", "data.js"):
        assert not re.search(
            r"(url\(\s*['\"]?https?:|@import\s+['\"]?https?:)", (SITE / name).read_text()
        )


def test_config_demo_url_placeholder():
    text = (SITE / "config.js").read_text(encoding="utf-8")
    assert re.search(r'^const DEMO_URL = "#";$', text, re.M)


def test_video_block_is_commented_out():
    p = _parse()
    assert "video" not in p.tags
    assert any("<video" in c for c in p.comments)


def test_sample_downloads_are_plain_anchors():
    hrefs = {v for t, a, v in _parse().refs if t == "a"}
    assert SAMPLE_DOWNLOADS <= hrefs


def test_repository_links():
    hrefs = {v for t, a, v in _parse().refs if t == "a"}
    assert "https://github.com/abhay-kumar-2501/tieout" in hrefs
    assert any(h.startswith("https://github.com/abhay-kumar-2501/tieout#") for h in hrefs)


def test_data_js_matches_committed_results():
    data = _js_object(SITE / "data.js", "TIEOUT")
    totals = json.loads((ROOT / "data/demo/results/results.json").read_text())["totals"]
    score = json.loads((ROOT / "data/demo/scorecard.json").read_text())
    l1 = totals["lever1"]
    assert data["naive"] == l1["naive"]
    assert data["defensible_recurring"] == totals["recurring"]
    assert data["lever1"]["defensible"] == l1["bridge"]["defensible"]
    assert data["lever1"]["steps"] == [l1["bridge_raw"][f"step_{i}"] for i in range(1, 8)]
    assert data["scorecard"]["held_out_seed"] == score["held_out_seed"]
    metrics = data["scorecard"]["metrics"]
    assert set(metrics) == set(score["tool"]["held_out"])
    for key, m in metrics.items():
        assert m["tool"] == score["tool"]["held_out"][key]
        assert m["baseline"] == score["baseline"]["held_out"][key]
        target = score["targets"].get(key)
        assert m["target"] == (target["bound"] if target else None)


def test_workflow_is_manual_only():
    text = (ROOT / ".github/workflows/pages.yml").read_text()
    assert "workflow_dispatch" in text
    assert not re.search(r"^\s*(push|pull_request|schedule):", text, re.M)
    for action in ("configure-pages", "upload-pages-artifact", "deploy-pages"):
        assert f"actions/{action}@" in text
