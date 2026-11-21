"""Small stylesheet for cards and typography (PRD 6.11 layout rules). No JavaScript."""

from __future__ import annotations

import streamlit as st

from tieout import theme as t

_CSS = f"""
<style>
.block-container {{
    max-width: {t.MAX_CONTENT_WIDTH}px;
    padding-top: {t.SPACING[2]}px;
}}
h1, h2, h3, h4 {{ color: {t.INK}; font-weight: 600; }}
.to-headline {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: 30px;
    line-height: 1.25;
    color: {t.INK};
    margin: {t.SPACING[1]}px 0 {t.SPACING[0]}px 0;
}}
.to-muted {{ color: {t.MUTED}; font-size: 15px; line-height: 1.5; }}
.to-caption {{ color: {t.MUTED}; font-size: 13px; }}
.to-mono {{ font-family: '{t.FONT_MONO}', monospace; font-size: 13px; }}
.to-num {{ font-variant-numeric: tabular-nums; text-align: right; }}
.to-card {{
    background: {t.SURFACE};
    border: {t.BORDER_WIDTH}px solid {t.BORDER};
    border-radius: {t.CARD_RADIUS}px;
    padding: {t.SPACING[1]}px {t.SPACING[2]}px;
    box-shadow: none;
}}
.to-tag {{
    display: inline-block;
    border: {t.BORDER_WIDTH}px solid {t.BORDER};
    border-radius: {t.CARD_RADIUS}px;
    padding: 2px {t.SPACING[0]}px;
    background: {t.AMBER_TINT};
    color: {t.INK};
    font-size: 12px;
}}
</style>
"""


def inject_style() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def headline(text: str) -> None:
    st.markdown(f'<div class="to-headline">{text}</div>', unsafe_allow_html=True)


def muted(text: str) -> None:
    st.markdown(f'<div class="to-muted">{text}</div>', unsafe_allow_html=True)
