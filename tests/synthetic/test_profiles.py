"""Named generator profiles (synthetic/profiles.py) and ``--profile`` on the command line."""

from __future__ import annotations

import pytest

from synthetic.__main__ import main
from synthetic.config import DEFAULT_CONFIG, GeneratorConfig
from synthetic.generate import generate
from synthetic.profiles import PROFILES, profile_config


def test_default_profile_is_the_documented_configuration() -> None:
    assert PROFILES["default"][1] == {}
    assert profile_config("default") == DEFAULT_CONFIG


def test_every_override_names_a_config_field() -> None:
    fields = set(GeneratorConfig.__dataclass_fields__)
    for name, (description, overrides) in PROFILES.items():
        assert description, name
        assert set(overrides) <= fields, name


def test_unknown_profile_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        profile_config("nope")


@pytest.mark.parametrize("name", [n for n in PROFILES if n != "default"])
def test_each_profile_generates_a_small_dataset(name: str) -> None:
    ds = generate(11, scale=0.1, config=profile_config(name))
    assert len(ds.lines["acquirer"]) > 0 and len(ds.lines["target"]) > 0
    assert not ds.truth_item_map.empty


def test_profiles_change_the_story() -> None:
    small = {n: generate(11, scale=0.1, config=profile_config(n)) for n in PROFILES}
    spend = {n: ds.lines["target"]["_usd"].sum() for n, ds in small.items()}
    assert spend["bolt_on"] < 0.5 * spend["default"]
    shared = {n: len(ds.world.shared) for n, ds in small.items()}
    assert shared["high_overlap"] > shared["default"]


def test_cli_accepts_a_profile(tmp_path) -> None:
    out = tmp_path / "bolt"
    args = ["--seed", "11", "--out", str(out), "--scale", "0.05", "--profile", "bolt_on"]
    assert main(args) == 0
    assert (out / "acquirer.csv").stat().st_size > 0
