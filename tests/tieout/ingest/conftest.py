"""Fixtures for the ingestion tests; the helpers live in ``ingest_fixtures``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
import pytest
from ingest_fixtures import CATEGORY_MAP, FX, Rows, make_raw

from tieout.ingest import Prepared, prepare
from tieout.reference import load_taxonomy


@pytest.fixture
def raw() -> Callable[..., pd.DataFrame]:
    return make_raw


@pytest.fixture
def run() -> Callable[..., Prepared]:
    def _run(acq: Rows, tgt: Rows | None = None, **kwargs: Any) -> Prepared:
        kwargs.setdefault("fx", FX)
        kwargs.setdefault("taxonomy", load_taxonomy())
        kwargs.setdefault("category_map", CATEGORY_MAP)
        return prepare(
            make_raw(acq, "acquirer"), make_raw(acq if tgt is None else tgt, "target"), **kwargs
        )

    return _run
