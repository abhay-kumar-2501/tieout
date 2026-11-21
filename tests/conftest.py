"""Fixtures shared across packages: a small generated dataset on disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from synthetic.generate import generate, write

SMALL_SEED = 7
SMALL_SCALE = 0.15


@pytest.fixture(scope="session")
def small_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """A 15% dataset written as the generator writes it: inputs in ``data/seeds/seed_7``
    and truth in ``data/truth/seed_7`` under a temporary root (``root`` in the result)."""
    root = tmp_path_factory.mktemp("small")
    out = root / "data" / "seeds" / f"seed_{SMALL_SEED}"
    truth = root / "data" / "truth" / f"seed_{SMALL_SEED}"
    paths = write(generate(SMALL_SEED, scale=SMALL_SCALE), out, truth)
    return {**paths, "root": root, "truth_dir": truth}
