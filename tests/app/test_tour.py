"""The guided tour: never automatic, five steps, one per signature moment (PRD 2.2, 6.2)."""

from __future__ import annotations

from pathlib import Path

from components.tour import IMAGE_DIR, STEPS
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"


def _text(at: AppTest) -> str:
    return "\n".join(str(e.value) for kind in ("markdown", "caption") for e in at.get(kind))


def _step_script() -> None:
    from components.tour import render_step

    render_step(in_dialog=False)


def test_five_steps_with_small_images_and_real_pages() -> None:
    assert [s.title for s in STEPS] == [
        "The bridge",
        "The scorecard",
        "The tie-out",
        "The price of resilience",
        "The unit trap",
    ]
    for step in STEPS:
        image = IMAGE_DIR / step.image
        assert image.is_file() and image.stat().st_size < 60_000
        assert (ROOT / "app" / "screens" / f"{step.page}.py").is_file()
        assert step.text and step.link


def test_tour_never_starts_automatically_and_opens_on_click() -> None:
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    assert not at.exception
    assert [b.label for b in at.button if b.key == "tour_open"] == ["Take the 2-minute tour"]
    assert "Step 1 of 5" not in _text(at)
    at.button(key="tour_open").click().run()
    assert not at.exception
    text = _text(at)
    assert "Step 1 of 5" in text and "The bridge" in text


def test_step_forward_and_back() -> None:
    at = AppTest.from_function(_step_script, default_timeout=60).run()
    assert "Step 1 of 5" in _text(at) and at.button(key="tour_back").disabled
    for number, step in enumerate(STEPS[1:], start=2):
        at.button(key="tour_next").click().run()
        assert not at.exception
        assert f"Step {number} of 5" in _text(at) and step.title in _text(at)
    assert at.button(key="tour_next").label == "Done"
    at.button(key="tour_back").click().run()
    assert "Step 4 of 5" in _text(at) and "The price of resilience" in _text(at)
    assert at.button(key="tour_next").label == "Next"
