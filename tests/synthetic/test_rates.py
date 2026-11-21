"""Each documented rate (PRD 8.2) lands within tolerance of its configured value."""

import pandas as pd
import pytest

from synthetic.config import COMPANIES
from synthetic.generate import Dataset
from synthetic.noise import ALIAS_KINDS


def _all_lines(ds: Dataset) -> pd.DataFrame:
    return pd.concat([ds.lines[c].assign(company=c) for c in COMPANIES], ignore_index=True)


def _vendor_views(ds: Dataset) -> list:
    return [v for c in COMPANIES for v in ds.vendors[c]]


def check_rates(ds: Dataset, tol: float) -> None:
    cfg, world = ds.config, ds.world
    views = _vendor_views(ds)

    # Vendors
    shared_parents = sum(p.shared for p in world.parents) / len(world.parents)
    assert shared_parents == pytest.approx(cfg.shared_parent_rate, abs=tol / 2)
    missing_tax = sum(v.tax_id == "" for v in views) / len(views)
    assert missing_tax == pytest.approx(cfg.tax_id_missing_rate, abs=tol)
    typos = sum("typo" in v.noise for v in views) / len(views)
    assert typos == pytest.approx(cfg.typo_rate, abs=tol)
    assert all(len(v.name) <= cfg.target_name_length for v in ds.vendors["target"])
    assert all(v.record.entity.country for v in views)
    shared_entities = {
        v.record.entity.entity_id for v in ds.vendors["acquirer"] if not v.record.duplicate
    } & {v.record.entity.entity_id for v in ds.vendors["target"] if not v.record.duplicate}
    aliased = {
        v.record.entity.entity_id
        for v in views
        if not v.record.duplicate
        and v.record.entity.entity_id in shared_entities
        and any(kind in ALIAS_KINDS for kind in v.noise.split("+"))
    }
    assert len(aliased) / len(shared_entities) == pytest.approx(cfg.alias_rate_shared, abs=2 * tol)
    nosim = sum(any(e.relation == "no_similarity" for e in p.entities) for p in world.parents)
    assert nosim / len(world.parents) == pytest.approx(cfg.no_similarity_parent_rate, abs=0.01)

    # Items
    n_records = sum(len(ds.items[c]) for c in COMPANIES)
    assert 2 * len(world.shared) / n_records == pytest.approx(cfg.shared_item_share, abs=0.01)
    both_mpn = sum(s.acquirer.has_mpn and s.target.has_mpn for s in world.shared) / len(
        world.shared
    )
    assert both_mpn == pytest.approx(cfg.mpn_both_sides_rate, abs=tol)
    packs = [h for s in world.shared for h in (s.acquirer, s.target) if h.pack_size and not h.trap]
    assert len(packs) / len(world.shared) == pytest.approx(cfg.pack_difference_rate, abs=0.01)
    modes = [h.pack_mode for h in packs]
    assert modes.count("text") / len(modes) == pytest.approx(0.5, abs=0.02)
    assert modes.count("column") / len(modes) == pytest.approx(0.25, abs=0.03)

    # Commercial
    lines = _all_lines(ds)
    assert (lines["payment_date"] != "").mean() == pytest.approx(cfg.payment_date_rate, abs=tol / 2)
    assert (lines["incoterm"] != "").mean() == pytest.approx(cfg.incoterm_rate, abs=tol / 2)
    assert lines["payment_terms_days"].notna().all()
    for code, share in cfg.currency_shares:
        assert (lines["currency"] == code).mean() == pytest.approx(share, abs=tol / 2)
    items = lines[(lines["item_code"] != "") | (lines["mpn"] != "")]
    contracted = items.loc[items["contract_id"] != "", "_usd"].sum() / items["_usd"].sum()
    assert contracted == pytest.approx(cfg.contract_spend_share, abs=tol)
    ends = pd.to_datetime(items.loc[items["contract_end_date"] != "", "contract_end_date"])
    assert ends.min() >= pd.Timestamp("2025-07-01") and ends.max() <= pd.Timestamp("2030-01-31")

    # Distractors
    d = ds.truth_distractors
    assert len(world.near_identical) >= 0.97 * cfg.count(cfg.near_identical_pairs)
    assert len(world.similar_vendor_pairs) == cfg.count(cfg.similar_vendor_pairs)
    assert (d["type"] == "freight_terms").sum() == cfg.count(cfg.freight_gap_items)
    assert (d["type"] == "unit_trap").sum() == cfg.count(cfg.unit_trap_count)
    assert (d["type"] == "spot_buy").sum() == pytest.approx(cfg.spot_buy_rate * n_records, abs=2)


def test_documented_rates_small(small):
    check_rates(small, tol=0.06)


@pytest.mark.slow
def test_documented_rates_full(full):
    check_rates(full, tol=0.03)


def test_unit_traps_meet_prd_minimum():
    from synthetic.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.unit_trap_count >= 60


def test_target_descriptions_truncated(small):
    for company in COMPANIES:
        limit = (
            small.config.target_description_length
            if company == "target"
            else small.config.acquirer_description_length
        )
        assert small.purchase_lines(company)["item_description"].str.len().max() <= limit
