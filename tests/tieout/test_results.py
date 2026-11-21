from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from tieout.results import FRAME_NAMES, Results


def test_empty_has_all_frames() -> None:
    res = Results.empty()
    assert all(getattr(res, name).empty for name in FRAME_NAMES)
    assert res.scorecard is None


def test_round_trip(tmp_path: Path) -> None:
    lines = pd.DataFrame({"line_id": ["acquirer:2"], "amount": [12.5], "uom": [None]})
    opps = pd.DataFrame({"id": ["L1:CI000001:switch"], "base": [4200.0]})
    res = Results(
        meta={"seed": 4, "view": "clean"},
        assumptions={"lever1": {"switch": {"low": 0.2}}},
        lines=lines,
        opportunities=opps,
        totals={"lever1": {"base": 4200.0}},
        trace={"L1:CI000001:switch": ["acquirer:2"]},
        scorecard={"precision": 0.9},
    )
    res.save(tmp_path / "out")
    loaded = Results.load(tmp_path / "out")
    assert_frame_equal(loaded.lines, lines)
    assert_frame_equal(loaded.opportunities, opps)
    assert loaded.meta == res.meta
    assert loaded.assumptions == res.assumptions
    assert loaded.totals == res.totals
    assert loaded.trace == res.trace
    assert loaded.scorecard == res.scorecard


def test_empty_round_trip(tmp_path: Path) -> None:
    Results.empty().save(tmp_path)
    loaded = Results.load(tmp_path)
    assert loaded.scorecard is None
    assert loaded.lines.empty


def test_frozen() -> None:
    with pytest.raises(AttributeError):
        Results.empty().meta = {}  # type: ignore[misc]
