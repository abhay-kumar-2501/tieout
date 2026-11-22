"""The committed sample mergers (data/samples.json) are real engine runs on unused seeds."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "data" / "samples.json").read_text(encoding="utf-8"))
SAMPLES = MANIFEST["samples"]
IDS = [s["id"] for s in SAMPLES]


def _script():
    spec = importlib.util.spec_from_file_location("make_samples", ROOT / "scripts/make_samples.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _results_json(sample: dict) -> dict:
    return json.loads((ROOT / sample["results"] / "results.json").read_text(encoding="utf-8"))


def test_manifest_is_what_the_script_writes() -> None:
    assert _script().manifest() == MANIFEST


def test_the_first_sample_is_the_held_out_demo_seed() -> None:
    first = SAMPLES[0]
    assert first["seed"] == MANIFEST["held_out_seed"] == 4
    assert first["profile"] == "default" and first["scale"] == 1.0
    assert first["results"] == "data/demo/results"
    assert first["scorecard"] == "data/demo/scorecard.json"


def test_extra_samples_use_new_seeds_and_distinct_profiles() -> None:
    assert 3 <= len(SAMPLES) <= 4 and len(set(IDS)) == len(IDS)
    extra = SAMPLES[1:]
    assert all(s["seed"] >= 5 for s in extra)
    assert len({s["seed"] for s in SAMPLES}) == len(SAMPLES)
    assert len({s["profile"] for s in SAMPLES}) == len(SAMPLES)


@pytest.mark.parametrize("sample", SAMPLES, ids=IDS)
def test_label_quotes_the_results_spend(sample: dict) -> None:
    spend = _results_json(sample)["meta"]["in_scope_spend"]["total"]
    assert sample["label"] == f"{sample['title']}, ${spend / 1e6:,.0f}M combined spend"


@pytest.mark.parametrize("sample", SAMPLES, ids=IDS)
def test_sample_figures_are_consistent(sample: dict) -> None:
    totals = _results_json(sample)["totals"]
    lever1, recurring = totals["lever1"], totals["recurring"]
    steps = [lever1["bridge_raw"][f"step_{i}"] for i in range(1, 8)]
    assert lever1["naive"] - sum(steps) == pytest.approx(lever1["bridge"]["defensible"], abs=1)
    assert 0 < recurring["low"] <= recurring["base"] <= recurring["high"] < lever1["naive"]


@pytest.mark.parametrize("sample", SAMPLES[1:], ids=IDS[1:])
def test_extra_sample_scorecard_is_its_own(sample: dict) -> None:
    card = json.loads((ROOT / sample["scorecard"]).read_text(encoding="utf-8"))
    assert card["held_out_seed"] == sample["seed"]
    assert card["sample"] == {"id": sample["id"], "profile": sample["profile"]}
    embedded = _results_json(sample)["scorecard"]
    assert embedded == card
    assert _results_json(sample)["sensitivity"]["curves"]


@pytest.mark.parametrize("sample", SAMPLES[1:], ids=IDS[1:])
def test_extra_samples_stay_light(sample: dict) -> None:
    size = sum(p.stat().st_size for p in (ROOT / sample["results"]).iterdir())
    assert size < 10_000_000, f"{sample['id']} results are {size / 1e6:.1f} MB"
