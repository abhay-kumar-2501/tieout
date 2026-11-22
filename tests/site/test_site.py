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
    manifest = json.loads((ROOT / "data/samples.json").read_text())["samples"]
    assert [s["id"] for s in data["samples"]] == [s["id"] for s in manifest]
    for sample, row in zip(data["samples"], manifest, strict=True):
        totals = json.loads((ROOT / row["results"] / "results.json").read_text())["totals"]
        l1 = totals["lever1"]
        assert sample["label"] == row["label"]
        assert sample["naive"] == l1["naive"]
        assert sample["defensible_recurring"] == totals["recurring"]
        assert sample["lever1"]["defensible"] == l1["bridge"]["defensible"]
        assert sample["lever1"]["steps"] == [l1["bridge_raw"][f"step_{i}"] for i in range(1, 8)]
    score = json.loads((ROOT / "data/demo/scorecard.json").read_text())
    assert data["scorecard"]["held_out_seed"] == score["held_out_seed"] == 4
    metrics = data["scorecard"]["metrics"]
    assert set(metrics) == set(score["tool"]["held_out"])
    for key, m in metrics.items():
        assert m["tool"] == score["tool"]["held_out"][key]
        assert m["baseline"] == score["baseline"]["held_out"][key]
        target = score["targets"].get(key)
        assert m["target"] == (target["bound"] if target else None)


def test_every_sample_has_its_own_downloads():
    from PIL import Image

    samples = _js_object(SITE / "data.js", "TIEOUT")["samples"]
    assert len(samples) >= 3
    assert samples[0]["assets"] == {
        "bridge": "assets/bridge.png",
        "workbook": "assets/tieout_workbook.xlsx",
        "deck": "assets/tieout_deck.pptx",
    }
    seen = set()
    for sample in samples:
        assets = sample["assets"]
        assert set(assets) == {"bridge", "workbook", "deck"}
        for rel in assets.values():
            assert (SITE / rel).is_file(), rel
            assert rel not in seen, rel
            seen.add(rel)
        # The page's <img> declares 2000 x 1080; every sample's bridge must match it.
        with Image.open(SITE / assets["bridge"]) as picture:
            assert picture.size == (2000, 1080), assets["bridge"]


def test_samples_tell_different_stories():
    samples = _js_object(SITE / "data.js", "TIEOUT")["samples"]
    assert len({round(s["naive"] / 1e6) for s in samples}) == len(samples)
    for s in samples:
        r = s["defensible_recurring"]
        assert 0 < r["low"] <= r["base"] <= r["high"] < s["naive"]


def test_sample_rotation_controls():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'id="next-sample"' in html and "Show another sample" in html
    assert 'data-bind="sample"' in html
    for asset in ("workbook", "deck", "bridge"):
        assert f'data-asset="{asset}"' in html
    script = (SITE / "main.js").read_text(encoding="utf-8")
    assert "Math.random()" in script and "TIEOUT.samples" in script


def test_workflow_is_manual_only():
    text = (ROOT / ".github/workflows/pages.yml").read_text()
    assert "workflow_dispatch" in text
    assert not re.search(r"^\s*(push|pull_request|schedule):", text, re.M)
    for action in ("configure-pages", "upload-pages-artifact", "deploy-pages"):
        assert f"actions/{action}@" in text


# ------------------------------------------------------------------ layout and type


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str | None]] = []
        self.metas: list[dict[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("img", "source"):
            self.images.append(dict(attrs))
        if tag == "meta":
            self.metas.append(dict(attrs))


def _tags() -> _Tags:
    p = _Tags()
    p.feed((SITE / "index.html").read_text(encoding="utf-8"))
    p.close()
    return p


def test_viewport_meta_is_present():
    assert any(
        m.get("name") == "viewport" and "width=device-width" in (m.get("content") or "")
        for m in _tags().metas
    )


def test_image_dimensions_match_the_files():
    from PIL import Image

    images = [a for a in _tags().images if (a.get("src") or "").startswith("assets/")]
    assert images, "no local images found"
    for a in images:
        with Image.open(SITE / a["src"]) as picture:
            assert (int(a["width"]), int(a["height"])) == picture.size, a["src"]


def _min_px(value: str, variables: dict[str, str]) -> float:
    """The smallest pixel size a CSS font-size value can resolve to."""
    value = value.strip()
    m = re.fullmatch(r"var\((--[\w-]+)\)", value)
    if m:
        return _min_px(variables[m.group(1)], variables)
    m = re.fullmatch(r"clamp\(\s*([^,]+),.*\)", value)
    if m:
        return _min_px(m.group(1), variables)
    m = re.fullmatch(r"([\d.]+)(px|rem)", value)
    assert m, f"unsupported font size {value!r}: use px, rem, clamp() or a token"
    return float(m.group(1)) * (16 if m.group(2) == "rem" else 1)


def test_every_text_size_is_at_least_14px():
    css = re.sub(r"/\*.*?\*/", "", (SITE / "styles.css").read_text(encoding="utf-8"), flags=re.S)
    variables = dict(re.findall(r"(--text-[\w-]+)\s*:\s*([^;]+);", css))
    sizes = re.findall(r"font-size\s*:\s*([^;}]+)", css)
    # The size in a font shorthand: "font: <weight> <size>/<line-height> <family>".
    sizes += re.findall(r"\bfont\s*:\s*\d{3}\s+(\S+?)/", css)
    sizes += variables.values()
    assert len(sizes) > 10
    for size in sizes:
        assert _min_px(size, variables) >= 14, size


def test_figures_come_from_data_js():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    text = re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", html, flags=re.S))
    assert not re.search(r"\$\s?\d", text), "hard-coded dollar figure in index.html"
    assert not re.search(r"\d%", text), "hard-coded percentage in index.html"
    assert 'data-bind="naive"' in html and 'data-bind="range"' in html
    script = (SITE / "main.js").read_text(encoding="utf-8")
    assert not re.search(r"[\"']\$?\d[\d.,]*[MkK%]?[\"']", script), "figure literal in main.js"
    assert "sample.naive" in script and "sample.defensible_recurring" in script
