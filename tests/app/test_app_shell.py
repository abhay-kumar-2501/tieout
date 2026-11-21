import tomllib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tieout import theme

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGE_PATHS = ["overview", "data", "matching", "synergies", "risk_roadmap", "assumptions",
              "export", "method_limits"]  # fmt: skip
VIEW_LABELS = ["Clean team", "Integration office"]


def test_app_renders():
    at = AppTest.from_file(str(MAIN), default_timeout=30).run()
    assert not at.exception
    assert at.session_state["view_mode"] == "Clean team"


@pytest.mark.parametrize("view_label", VIEW_LABELS)
@pytest.mark.parametrize("page", PAGE_PATHS)
def test_each_page_renders_in_both_view_modes(page, view_label):
    at = AppTest.from_file(str(MAIN), default_timeout=30)
    at.session_state["view_mode"] = view_label
    at.run()
    at.switch_page(str(ROOT / "app" / "pages" / f"{page}.py")).run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["view_mode"] == view_label


@pytest.mark.parametrize("page", PAGE_PATHS)
def test_page_module_runs_standalone(page):
    at = AppTest.from_file(str(ROOT / "app" / "pages" / f"{page}.py"), default_timeout=30)
    at.run()
    assert not at.exception


def test_config_hexes_match_tokens():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    t = cfg["theme"]
    assert t["primaryColor"] == theme.TEAL
    assert t["backgroundColor"] == theme.PAPER
    assert t["secondaryBackgroundColor"] == theme.SURFACE
    assert t["textColor"] == theme.INK
    assert t["linkColor"] == theme.TEAL
    assert t["borderColor"] == theme.BORDER
    assert t["base"] == "light"
    assert cfg["server"]["maxUploadSize"] == 50
    assert cfg["server"]["enableStaticServing"] is True


def test_config_fonts_match_tokens_and_files_exist():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    t = cfg["theme"]
    assert t["font"].startswith(theme.FONT_SANS)
    assert t["codeFont"].startswith(theme.FONT_MONO)
    families = {f["family"] for f in t["fontFaces"]}
    assert families == {theme.FONT_SANS, theme.FONT_SERIF, theme.FONT_MONO}
    for face in t["fontFaces"]:
        path = ROOT / "app" / "static" / "fonts" / Path(face["url"]).name
        assert path.read_bytes()[:4] == b"wOF2"


def test_theme_tokens_are_valid_hexes_and_streamlit_free():
    import re

    assert all(re.fullmatch(r"#[0-9A-F]{6}", v) for v in theme.COLORS.values())
    src = (ROOT / "tieout" / "theme.py").read_text()
    assert "streamlit" not in src.replace("must not import streamlit", "")
