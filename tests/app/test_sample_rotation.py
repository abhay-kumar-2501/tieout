"""The app rotates between the committed sample mergers (data/samples.json)."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGES = ROOT / "app" / "screens"
MANIFEST = json.loads((ROOT / "data" / "samples.json").read_text(encoding="utf-8"))["samples"]
IDS = [s["id"] for s in MANIFEST]
LABELS = {s["id"]: s["label"] for s in MANIFEST}
SCREENS = [
    "overview",
    "data",
    "matching",
    "synergies",
    "risk_roadmap",
    "assumptions",
    "export",
    "method_limits",
]


def _texts(at: AppTest) -> str:
    out = [str(e.value) for kind in ("markdown", "caption", "info") for e in at.get(kind)]
    return html.unescape("\n".join(out))


def _state_script() -> None:
    import streamlit as st
    from components import state

    for op, args in st.session_state.pop("ops", []):
        getattr(state, op)(*args)
    results = state.current_results()
    st.session_state["out"] = {
        "sample": state.sample().id,
        "is_demo": state.is_demo(),
        "naive": float(results.totals["lever1"]["naive"]),
        "decisions": len(state.decisions()),
        "scenarios": sorted(state.scenarios()),
        "overrides": state.assumptions()["lever1"]["same_vendor"]["base"],
    }


def _state(*ops: tuple[str, tuple]) -> AppTest:
    at = AppTest.from_function(_state_script, default_timeout=60)
    at.session_state["ops"] = list(ops)
    return at.run()


def test_samples_come_from_the_manifest() -> None:
    from components import state

    found = state._load_samples(str(state.SAMPLES_FILE))
    assert [s.id for s in found] == IDS
    assert found[0].results_dir == state.DEMO_DIR


def test_a_new_session_picks_a_random_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIEOUT_SAMPLE")
    seen = set()
    for _ in range(12):
        out = _state().session_state["out"]
        assert out["sample"] in IDS and out["is_demo"]
        seen.add(out["sample"])
    assert len(seen) > 1  # 12 draws from 4 all landing on one sample: about 1 in 2 million


@pytest.mark.parametrize("sample_id", IDS)
def test_each_sample_loads_its_own_results(sample_id: str, monkeypatch) -> None:
    monkeypatch.setenv("TIEOUT_SAMPLE", sample_id)
    out = _state().session_state["out"]
    committed = json.loads(
        (ROOT / MANIFEST[IDS.index(sample_id)]["results"] / "results.json").read_text()
    )
    assert out["sample"] == sample_id
    assert out["naive"] == pytest.approx(committed["totals"]["lever1"]["naive"])


def test_switching_sample_clears_work_and_keeps_scenarios() -> None:
    at = _state(
        ("set_assumptions", ({"lever1": {"same_vendor": {"base": 0.5}}},)),
        ("save_scenario", ("Board case",)),
    )
    assert at.session_state["out"]["overrides"] == 0.5
    at.session_state["ops"] = [("set_sample", (IDS[1],))]
    out = at.run().session_state["out"]
    assert out["sample"] == IDS[1] and out["is_demo"]
    assert out["overrides"] != 0.5 and out["decisions"] == 0
    assert out["scenarios"] == ["Board case"]


def test_unknown_sample_is_refused() -> None:
    at = _state(("set_sample", ("nope",)))
    assert at.exception


def test_back_to_demo_returns_to_the_chosen_sample() -> None:
    from tieout.results import Results

    uploaded = Results.load(ROOT / MANIFEST[0]["results"])
    at = _state(("set_sample", (IDS[2],)), ("set_uploaded_results", (uploaded,)))
    assert not at.session_state["out"]["is_demo"]
    at.session_state["ops"] = [("reset_to_demo", ())]
    out = at.run().session_state["out"]
    assert out["is_demo"] and out["sample"] == IDS[2]


def test_header_names_the_sample(monkeypatch) -> None:
    monkeypatch.setenv("TIEOUT_SAMPLE", IDS[1])
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    assert not at.exception
    assert LABELS[IDS[1]] in _texts(at)


def test_data_screen_switches_sample() -> None:
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    at.switch_page(str(PAGES / "data.py")).run()
    picker = at.selectbox(key=f"data_sample_{IDS[0]}")
    assert list(picker.options) == [LABELS[i] for i in IDS]
    picker.set_value(IDS[3]).run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["_to_sample"] == IDS[3]
    assert at.selectbox(key=f"data_sample_{IDS[3]}").value == IDS[3]


@pytest.mark.parametrize("screen", SCREENS)
@pytest.mark.parametrize("sample_id", IDS[1:])
def test_every_screen_loads_for_every_sample(sample_id: str, screen: str, monkeypatch) -> None:
    monkeypatch.setenv("TIEOUT_SAMPLE", sample_id)
    at = AppTest.from_file(str(MAIN), default_timeout=120).run()
    if screen != "overview":
        at.switch_page(str(PAGES / f"{screen}.py")).run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["_to_sample"] == sample_id
    assert len(at.markdown) > 3
