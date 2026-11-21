"""Scale (PRD 8.1), calibration bounds (PRD 8.3) and the command line."""

import time

import pytest

from synthetic.__main__ import main
from synthetic.config import COMPANIES
from synthetic.generate import Dataset, generate
from synthetic.summary import summarise

PRD_SHAPE = {
    "acquirer": {
        "lines": 38_000,
        "vendor_records": 1_500,
        "item_records": 5_500,
        "sites": 8,
        "spend": 340e6,
    },
    "target": {
        "lines": 22_000,
        "vendor_records": 1_000,
        "item_records": 3_500,
        "sites": 5,
        "spend": 180e6,
    },
}


def check_shape(ds: Dataset) -> None:
    scale = ds.config.scale
    for company in COMPANIES:
        df = ds.lines[company]
        want = PRD_SHAPE[company]
        got = {
            "lines": len(df),
            "vendor_records": df["vendor_id"].nunique(),
            "item_records": len(ds.items[company]),
            "spend": df["_usd"].sum(),
        }
        for key, value in got.items():
            assert value == pytest.approx(want[key] * scale, rel=0.25), (company, key)
        assert df["site"].nunique() == want["sites"]
        no_item = (
            df.loc[(df["item_code"] == "") & (df["mpn"] == ""), "_usd"].sum() / df["_usd"].sum()
        )
        assert no_item == pytest.approx(0.35, abs=0.05)


def test_small_dataset_is_proportionate(small):
    check_shape(small)


@pytest.mark.slow
def test_full_size_matches_prd_and_is_fast():
    start = time.perf_counter()
    ds = generate(4)
    assert time.perf_counter() - start < 60
    check_shape(ds)
    s = summarise(ds)
    assert 3.0 <= s["naive_proxy_pct_of_spend"] <= 9.0
    assert 0.8 <= s["lever1_base_proxy_pct_of_spend"] <= 3.0


def test_cli_writes_inputs_and_truth(tmp_path, capsys):
    out, truth = tmp_path / "demo", tmp_path / "truth" / "seed_9"
    assert (
        main(
            [
                "--seed",
                "9",
                "--out",
                str(out),
                "--truth-dir",
                str(truth),
                "--scale",
                "0.03",
                "--summary",
            ]
        )
        == 0
    )
    for name in ("acquirer.csv", "target.csv", "vendor_parents.csv", "category_map.csv"):
        assert (out / name).stat().st_size > 0
    for name in ("truth_vendor_map.csv", "truth_item_map.csv", "truth_savings.csv"):
        assert (truth / name).stat().st_size > 0
    assert not (out / "truth").exists()
    printed = capsys.readouterr().out
    assert "planted_gross_gap_pct_of_spend" in printed and "unit_traps" in printed
