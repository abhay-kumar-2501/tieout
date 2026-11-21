import copy

import pytest

from tieout.assumptions import DEFAULTS, merge_overrides, validate


def test_defaults_are_valid() -> None:
    validate(DEFAULTS)


def test_merge_overrides_is_deep_and_non_mutating() -> None:
    before = copy.deepcopy(DEFAULTS)
    merged = merge_overrides({"lever1": {"switch": {"base": 0.5}}, "cost_of_capital": 0.1})
    assert merged["lever1"]["switch"] == {"low": 0.20, "base": 0.5, "high": 0.60}
    assert merged["lever1"]["same_vendor"] == DEFAULTS["lever1"]["same_vendor"]
    assert merged["cost_of_capital"] == 0.1
    assert DEFAULTS == before
    assert merge_overrides(None) == DEFAULTS


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lever1": {"switch": {"low": 0.5, "base": 0.4}}}, "lever1.switch"),
        ({"lever2": {"capture": {"high": 1.2}}}, "lever2.capture"),
        ({"lever3": {"capture": {"low": -0.1}}}, "lever3.capture"),
        ({"lever2": {"discount": {"mro": 1.5}}}, "lever2.discount.mro"),
        ({"caps": {"critical": -0.2}}, "caps.critical"),
        ({"reference_bands": {"total_spend": {"low": 0.05, "high": 0.01}}}, "reference_bands"),
        ({"cost_of_capital": "8%"}, "cost_of_capital"),
    ],
)
def test_bad_values_rejected(overrides: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate(merge_overrides(overrides))


def test_missing_key_rejected() -> None:
    bad = copy.deepcopy(DEFAULTS)
    del bad["caps"]
    with pytest.raises(ValueError, match="missing assumption: caps"):
        validate(bad)
