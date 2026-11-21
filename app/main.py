"""Tie-Out entry point: `streamlit run app/main.py`."""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402
from components.header import render_header  # noqa: E402
from components.style import inject_style  # noqa: E402

PAGES = [
    ("Overview", "overview"),
    ("Data", "data"),
    ("Matching", "matching"),
    ("Synergies", "synergies"),
    ("Risk & roadmap", "risk_roadmap"),
    ("Assumptions", "assumptions"),
    ("Export", "export"),
    ("Method & limits", "method_limits"),
]

st.set_page_config(page_title="Tie-Out", layout="wide", initial_sidebar_state="collapsed")

pages = [
    st.Page(str(APP_DIR / "pages" / f"{module}.py"), title=title, url_path=module, default=i == 0)
    for i, (title, module) in enumerate(PAGES)
]
current = st.navigation(pages, position="top")
inject_style()
render_header()
current.run()
