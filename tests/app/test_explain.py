"""Plain words for a newcomer: Explore cards, screen introductions, glossary and the
sample switch in the header."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest
from components.explain import EXPLORE, GLOSSARY, STEP_REASONS
from streamlit.testing.v1 import AppTest

from tieout.results import Results
from tieout.views import bridge

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGES = ROOT / "app" / "screens"
SCREENS = ["data", "matching", "synergies", "risk_roadmap", "assumptions", "export",
           "method_limits"]  # fmt: skip
MANIFEST = json.loads((ROOT / "data" / "samples.json").read_text(encoding="utf-8"))["samples"]


def _markdown(at: AppTest) -> str:
    return html.unescape("\n".join(str(m.value) for m in at.markdown))


def test_explore_cards_cover_every_other_screen_once() -> None:
    modules = [card.module for card in EXPLORE]
    assert sorted(modules) == sorted(SCREENS)
    for card in EXPLORE:
        assert (PAGES / f"{card.module}.py").is_file()
        assert card.question.endswith("?") and card.action and card.icon


def test_overview_links_every_explore_card_to_its_page() -> None:
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    assert not at.exception, [e.message for e in at.exception]
    links = {p.label: p.proto.page for p in at.get("page_link")}
    for card in EXPLORE:
        assert card.action in links, card.action
        assert links[card.action].endswith(f"{card.module}.py") or links[card.action] == (
            card.module
        )
    text = _markdown(at)
    for card in EXPLORE:
        assert card.question in text
    # The tour is offered twice (hero and card), and both buttons open the same tour.
    keys = [b.key for b in at.button if b.label == "Take the 2-minute tour"]
    assert keys == ["tour_open", "tour_open_card"]
    at.button(key="tour_open_card").click().run()
    assert "Step 1 of 5" in "\n".join(str(c.value) for c in at.caption)


@pytest.mark.parametrize("screen", SCREENS)
def test_every_screen_opens_with_a_plain_introduction(screen: str) -> None:
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    at.switch_page(str(PAGES / f"{screen}.py")).run()
    assert not at.exception, [e.message for e in at.exception]
    assert 'class="to-intro"' in _markdown(at)


@pytest.mark.parametrize("sample", [s["results"] for s in MANIFEST])
def test_every_bridge_bar_has_a_plain_reason(sample: str) -> None:
    results = Results.load(ROOT / sample)
    for mode in ("clean", "masked"):
        for label in bridge(results, mode)["label"]:
            assert STEP_REASONS.get(label), label


def test_glossary_on_method_and_limits() -> None:
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    at.switch_page(str(PAGES / "method_limits.py")).run()
    text = _markdown(at)
    for term in GLOSSARY:
        assert html.unescape(term) in text


def test_header_offers_the_other_samples() -> None:
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    assert "You're looking at" in _markdown(at)
    current = next(b for b in at.button if b.key == f"header_sample_{MANIFEST[0]['id']}")
    assert current.disabled
    target = MANIFEST[2]
    at.button(key=f"header_sample_{target['id']}").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["_to_sample"] == target["id"]
    assert target["label"] in _markdown(at)
