"""Review decisions model (PRD 4.5)."""

import io

import pandas as pd
import pytest

from tieout.match.review import (
    DECISION_COLUMNS,
    approved,
    decision_for,
    deferred,
    empty_decisions,
    latest_decisions,
    make_pair_id,
    parse_pair_id,
    read_decisions_csv,
    record_decision,
    rejected,
    undo_last,
    write_decisions_csv,
)

T0 = "2026-01-01T00:00:00Z"


def test_pair_id_sorts_sides() -> None:
    assert make_pair_id("vendor_match", "target:T1", "acquirer:V9") == (
        "vendor_match|acquirer:V9|target:T1"
    )
    assert make_pair_id("item_match", "a:1", "b:2") == make_pair_id("item_match", "b:2", "a:1")
    assert parse_pair_id("unit_flag|acquirer:X|target:Y") == ("unit_flag", "acquirer:X", "target:Y")


def test_pair_id_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        make_pair_id("vendor", "a:1", "b:2")
    with pytest.raises(ValueError):
        parse_pair_id("vendor_match|only-one-side")


def test_empty_decisions_schema() -> None:
    frame = empty_decisions()
    assert tuple(frame.columns) == DECISION_COLUMNS and frame.empty


def test_record_decision_appends_and_infers_type() -> None:
    pid = make_pair_id("unit_flag", "acquirer:1", "target:2")
    log = record_decision(None, pid, "approve", pack_qty=12, note="box of 12")
    assert log.loc[0, "type"] == "unit_flag"
    assert log.loc[0, "pack_qty"] == 12.0
    assert log.loc[0, "decided_at"].endswith("Z")
    with pytest.raises(ValueError):
        record_decision(log, pid, "maybe")


def test_latest_decision_wins_and_lookups_by_type() -> None:
    a = make_pair_id("vendor_match", "acquirer:1", "target:1")
    b = make_pair_id("vendor_sibling", "acquirer:2", "target:2")
    c = make_pair_id("item_match", "acquirer:3", "target:3")
    log = record_decision(None, a, "reject", decided_at=T0)
    log = record_decision(log, a, "approve", decided_at=T0)
    log = record_decision(log, b, "reject", decided_at=T0)
    log = record_decision(log, c, "defer", decided_at=T0)
    assert approved(log) == {a}
    assert rejected(log) == {b}
    assert deferred(log) == {c}
    assert approved(log, "vendor_sibling") == frozenset()
    assert decision_for(log, a) == "approve"
    assert decision_for(log, "vendor_match|x:1|y:1") is None
    assert len(latest_decisions(log)) == 3


def test_undo_removes_only_the_last_decision() -> None:
    a = make_pair_id("vendor_match", "acquirer:1", "target:1")
    log = record_decision(None, a, "reject", decided_at=T0)
    log = record_decision(log, a, "approve", decided_at=T0)
    assert decision_for(undo_last(log), a) == "reject"
    assert undo_last(undo_last(log)).empty
    assert undo_last(empty_decisions()).empty


def test_csv_round_trip() -> None:
    log = record_decision(
        None, make_pair_id("unit_flag", "acquirer:1", "target:2"), "approve", pack_qty=12
    )
    log = record_decision(
        log,
        make_pair_id("vendor_match", "acquirer:1", "target:2"),
        "reject",
        note='different firms, "Acme" vs "Acme Labs"',
        decided_at=T0,
    )
    text = write_decisions_csv(log)
    assert text.splitlines()[0] == ",".join(DECISION_COLUMNS)
    pd.testing.assert_frame_equal(read_decisions_csv(io.StringIO(text)), log)
    pd.testing.assert_frame_equal(read_decisions_csv(text), log)


def test_csv_file_round_trip(tmp_path) -> None:
    log = record_decision(
        None, make_pair_id("incoterm", "acquirer:1", "target:2"), "defer", decided_at=T0
    )
    path = tmp_path / "decisions.csv"
    write_decisions_csv(log, path)
    pd.testing.assert_frame_equal(read_decisions_csv(path), log)


def test_import_rejects_mismatched_type() -> None:
    text = (
        "pair_id,type,decision,pack_qty,note,decided_at\n"
        "vendor_match|a:1|b:2,item_match,approve,,,\n"
    )
    with pytest.raises(ValueError):
        read_decisions_csv(text)
