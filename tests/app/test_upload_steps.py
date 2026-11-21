"""The stepper's plain logic: which step is next and what stops the flow."""

from __future__ import annotations

import pandas as pd
from components import upload_steps as steps

from tieout.ingest.schema import REQUIRED
from tieout.upload import UploadCheck

FULL = {h: h for h in REQUIRED}
BOTH = {"acquirer": object(), "target": object()}


def _check(blocked: bool) -> UploadCheck:
    return UploadCheck(blocked, pd.DataFrame(), pd.DataFrame(), {}, 0.0)


def test_five_steps_in_the_prd_order() -> None:
    assert steps.STEPS == ("Upload", "Map columns", "Validate", "Map categories", "Run")


def test_upload_needs_both_files() -> None:
    assert steps.blockers(0, steps.Facts()) == [
        "Add the acquirer file.",
        "Add the target file.",
    ]
    assert steps.blockers(0, steps.Facts(files={"acquirer": 1})) == ["Add the target file."]
    assert steps.blockers(0, steps.Facts(files=BOTH)) == []


def test_mapping_needs_every_required_field_in_both_files() -> None:
    short = {h: f for h, f in FULL.items() if f != "currency"}
    facts = steps.Facts(files=BOTH, mapping={"acquirer": FULL, "target": short})
    assert steps.blockers(1, facts) == [
        "Target: No column is mapped to the required field currency."
    ]
    assert steps.blockers(1, steps.Facts(mapping={"acquirer": FULL, "target": FULL})) == []


def test_blocking_validation_stops_the_flow() -> None:
    assert steps.blockers(2, steps.Facts()) == ["Validation has not run yet."]
    assert steps.blockers(2, steps.Facts(check=_check(True)))
    assert steps.blockers(2, steps.Facts(check=_check(False))) == []


def test_categories_need_at_least_one_mapping() -> None:
    assert steps.blockers(3, steps.Facts(mapped_categories=0))
    assert steps.blockers(3, steps.Facts(mapped_categories=2)) == []


def test_advance_moves_one_step_only_when_nothing_blocks() -> None:
    assert steps.advance(0, steps.Facts()) == 0
    assert steps.advance(0, steps.Facts(files=BOTH)) == 1
    assert steps.advance(2, steps.Facts(check=_check(True))) == 2
    assert steps.advance(4, steps.Facts()) == 4  # Run is the last step


def test_a_change_makes_later_work_stale() -> None:
    assert steps.stale_after(0) == ("mapping", "check", "categories", "run_error")
    assert steps.stale_after(1) == ("check", "categories", "run_error")
    assert steps.stale_after(3) == ()


def test_status_marks_done_current_and_todo() -> None:
    marks = [state for _, state in steps.step_status(2)]
    assert marks == ["done", "done", "current", "todo", "todo"]
