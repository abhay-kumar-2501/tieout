import hashlib

import pandas as pd

from synthetic.config import COMPANIES
from synthetic.generate import generate, write

TRUTH_FRAMES = (
    "vendor_parents",
    "category_map",
    "truth_vendor_map",
    "truth_item_map",
    "truth_savings",
)


def test_same_seed_gives_identical_frames(small):
    again = generate(small.seed, scale=small.config.scale)
    for company in COMPANIES:
        pd.testing.assert_frame_equal(small.purchase_lines(company), again.purchase_lines(company))
    for name in TRUTH_FRAMES:
        pd.testing.assert_frame_equal(getattr(small, name), getattr(again, name))


def test_same_seed_gives_byte_identical_files(tmp_path):
    digests = []
    for run in ("a", "b"):
        ds = generate(3, scale=0.05)
        paths = write(ds, tmp_path / run)
        digests.append(
            {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in sorted(paths.items())}
        )
    assert digests[0] == digests[1]


def test_different_seeds_differ(small):
    other = generate(small.seed + 1, scale=small.config.scale)
    assert not small.purchase_lines("acquirer").equals(other.purchase_lines("acquirer"))
