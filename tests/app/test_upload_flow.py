"""The "Use your own data" flow driven end to end (PRD 2.3, 6.13, 9.3)."""

from __future__ import annotations

import html
import io
import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.errors import AppTestError

from tieout import upload

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
DATA = ROOT / "app" / "screens" / "data.py"
UPLOADED = "_to_uploaded"


def _text(at: AppTest) -> str:
    out = [str(e.value) for kind in ("markdown", "caption", "info", "error", "success", "warning")
           for e in at.get(kind)]  # fmt: skip
    for frame in at.dataframe:
        out += [str(v) for v in frame.value.to_numpy().ravel()]
    return html.unescape("\n".join(out))


def _fresh() -> AppTest:
    at = AppTest.from_file(str(MAIN), default_timeout=120)
    at.run()
    at.switch_page(str(DATA)).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _upload(at: AppTest, acquirer: bytes, target: bytes) -> AppTest:
    at.button(key="data_use_own").click().run()
    at.file_uploader(key="up_file_acquirer_0").set_value(("acquirer.csv", acquirer, "text/csv"))
    at.file_uploader(key="up_file_target_0").set_value(("target.csv", target, "text/csv"))
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _next(at: AppTest) -> AppTest:
    at.button(key="up_next").click().run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _step(at: AppTest) -> int:
    return int(at.session_state["_up_step"])


@pytest.fixture(scope="module")
def files(small_files: dict[str, Path]) -> dict[str, bytes]:
    return {c: small_files[c].read_bytes() for c in ("acquirer", "target", "category_map")}


@pytest.fixture(scope="module")
def finished(files: dict[str, bytes]) -> Iterator[tuple[AppTest, list[str]]]:
    """The whole flow run once, with the working directory empty and watched for writes."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as cwd:
        before = os.getcwd()
        os.chdir(cwd)
        try:
            at = _upload(_fresh(), files["acquirer"], files["target"])
            for _ in range(3):  # Upload, Map columns, Validate -> Map categories
                _next(at)
            assert _step(at) == 3
            at.file_uploader(key="up_cat_file").set_value(
                ("category_map.csv", files["category_map"], "text/csv")
            )
            at.run()
            assert "The file set" in _text(at)
            _next(at)
            assert _step(at) == 4
            at.button(key="up_run").click().run()
            written = sorted(p.name for p in Path(cwd).rglob("*"))
        finally:
            os.chdir(before)
        yield at, written


def test_upload_reaches_results(finished: tuple[AppTest, list[str]]) -> None:
    at, _ = finished
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state[UPLOADED] is not None  # is_demo() is now false
    text = _text(at)
    assert "These are your uploaded files" in text
    assert "acquirer.csv" in text and "target.csv" in text
    assert "_up_files" not in at.session_state  # the raw files are dropped after the run
    assert [b.label for b in at.button if b.key == "data_back_to_demo"] == ["Back to demo"]


def test_upload_writes_nothing_to_disk(finished: tuple[AppTest, list[str]]) -> None:
    assert finished[1] == []


def test_back_to_demo_restores_the_demo_headline(
    finished: tuple[AppTest, list[str]], files: dict[str, bytes]
) -> None:
    at, _ = finished
    uploaded_rows = len(pd.read_csv(io.BytesIO(files["acquirer"]))) + len(
        pd.read_csv(io.BytesIO(files["target"]))
    )
    assert f"{uploaded_rows:,} purchasing lines" in _text(at)
    at.button(key="data_back_to_demo").click().run()
    assert not at.exception
    assert UPLOADED not in at.session_state or at.session_state[UPLOADED] is None
    text = _text(at)
    assert "60,012 purchasing lines" in text  # the committed demo: 38,006 + 22,006
    assert at.button(key="data_use_own").label == "Use your own data"


def test_stepper_shows_privacy_notice_and_limits(files: dict[str, bytes]) -> None:
    at = _fresh()
    at.button(key="data_use_own").click().run()
    text = _text(at)
    assert "not a place for real deal data" in text
    assert "250,000 rows" in text and "50 MB" in text
    for label in ("1. Upload", "2. Map columns", "3. Validate", "4. Map categories", "5. Run"):
        assert label in text
    assert at.button(key="up_next").disabled  # no files yet
    assert "Add the acquirer file." in text


def test_a_file_over_the_row_limit_is_refused(
    files: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upload, "MAX_ROWS", 100)
    at = _upload(_fresh(), files["acquirer"], files["target"])
    text = _text(at)
    assert "was refused" in text and "more than 100 rows" in text
    assert _step(at) == 0
    assert at.button(key="up_next").disabled


def test_a_missing_required_column_stops_at_the_mapping(files: dict[str, bytes]) -> None:
    target = files["target"].replace(b",currency,", b",ccy,", 1)  # a header no suggestion finds
    at = _upload(_fresh(), files["acquirer"], target)
    _next(at)
    assert _step(at) == 1
    text = _text(at)
    assert "Target: No column is mapped to the required field currency." in text
    assert at.button(key="up_next").disabled
    with pytest.raises(AppTestError):  # a browser user cannot click a disabled button
        at.button(key="up_next").click()
    assert _step(at) == 1


def test_blocking_validation_errors_stop_the_flow(files: dict[str, bytes]) -> None:
    frame = pd.read_csv(io.BytesIO(files["target"]), dtype=str, keep_default_na=False)
    frame.loc[frame.index[: len(frame) // 10], "doc_date"] = "not a date"
    broken = frame.to_csv(index=False).encode()
    at = _upload(_fresh(), files["acquirer"], broken)
    _next(at)
    _next(at)
    assert _step(at) == 2
    errors = [html.unescape(str(e.value)) for e in at.error]
    assert errors and "Target" in errors[0]
    assert at.button(key="up_next").disabled
    assert "Go back, correct the file" in _text(at)
    assert _step(at) == 2


def test_mapping_edits_survive_a_visit_to_another_step(files: dict[str, bytes]) -> None:
    at = _upload(_fresh(), files["acquirer"], files["target"])
    _next(at)
    at.selectbox(key="up_map_target_0").set_value("").run()  # site: not used
    at.button(key="up_prev").click().run()
    _next(at)
    assert at.selectbox(key="up_map_target_0").value == ""
    assert at.button(key="up_next").disabled  # site is required and no longer mapped


def _to_run(at: AppTest, category_map: bytes) -> AppTest:
    for _ in range(3):
        _next(at)
    at.file_uploader(key="up_cat_file").set_value(("category_map.csv", category_map, "text/csv"))
    at.run()
    _next(at)
    assert _step(at) == 4
    at.button(key="up_run").click().run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def test_optional_inputs_reach_the_run(
    files: dict[str, bytes], small_files: dict[str, Path]
) -> None:
    at = _upload(_fresh(), files["acquirer"], files["target"])
    parents = small_files["vendor_parents"].read_bytes()
    at.file_uploader(key="up_opt_file_vendor_parents_0").set_value(
        ("vendor_parents.csv", parents, "text/csv")
    )
    at.toggle(key="up_opt_period_on").set_value(True)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.button(key="up_next").disabled
    _to_run(at, files["category_map"])
    results_meta = at.session_state[UPLOADED].meta
    assert results_meta["inputs"]["vendor_parents"] is True
    assert re.fullmatch(r"\d{4}-\d{2}", results_meta["period"]["end"])


def test_a_malformed_fx_file_shows_a_message_and_blocks(files: dict[str, bytes]) -> None:
    at = _upload(_fresh(), files["acquirer"], files["target"])
    at.file_uploader(key="up_opt_file_fx_0").set_value(
        ("fx.csv", b"cur,rate\nEUR,1.1\n", "text/csv")
    )
    at.run()
    errors = [html.unescape(str(e.value)) for e in at.error]
    assert any("FX rates file needs the columns currency, rate" in e for e in errors)
    assert at.button(key="up_next").disabled
    assert _step(at) == 0
