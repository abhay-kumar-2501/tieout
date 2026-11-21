"""Seeded datasets on disk: generated on demand, inputs and truth kept apart (PRD 4.7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synthetic.generate import generate, write

TUNING_SEEDS = (1, 2, 3)
HELD_OUT_SEED = 4
DEFAULT_SEEDS_DIR = Path("data/seeds")
DEFAULT_TRUTH_DIR = Path("data/truth")
_INPUTS = ("acquirer.csv", "target.csv", "vendor_parents.csv", "category_map.csv")


@dataclass(frozen=True)
class SeedFiles:
    """Where one seed's inputs and truth live."""

    seed: int
    inputs: Path
    truth: Path

    @property
    def acquirer(self) -> Path:
        return self.inputs / "acquirer.csv"

    @property
    def target(self) -> Path:
        return self.inputs / "target.csv"

    @property
    def vendor_parents(self) -> Path:
        return self.inputs / "vendor_parents.csv"

    @property
    def category_map(self) -> Path:
        return self.inputs / "category_map.csv"


def ensure_seed(
    seed: int,
    seeds_dir: str | Path = DEFAULT_SEEDS_DIR,
    truth_dir: str | Path = DEFAULT_TRUTH_DIR,
) -> SeedFiles:
    """Generate seed ``seed`` unless its inputs are already on disk.

    Inputs go to ``seeds_dir/seed_{n}`` and truth to ``truth_dir/seed_{n}``.
    Generation is byte-identical per seed, so regenerating over committed truth
    leaves it unchanged.
    """
    files = SeedFiles(seed, Path(seeds_dir) / f"seed_{seed}", Path(truth_dir) / f"seed_{seed}")
    present = all((files.inputs / name).is_file() for name in _INPUTS)
    if not present or not (files.truth / "truth_item_map.csv").is_file():
        write(generate(seed), files.inputs, files.truth)
    return files
