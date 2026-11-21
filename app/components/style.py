"""Small stylesheet for cards and typography (PRD 6.11 layout rules). No JavaScript."""

from __future__ import annotations

from html import escape

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
    margin: {t.SPACING[0]}px 0 {t.SPACING[1]}px 0;
}}
.to-question {{
    color: {t.MUTED};
    font-size: 13px;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    margin-top: {t.SPACING[1]}px;
}}
.to-section {{
    font-family: '{t.FONT_SANS}', sans-serif;
    font-weight: 600;
    font-size: 19px;
    color: {t.INK};
    margin: {t.SPACING[2]}px 0 {t.SPACING[0]}px 0;
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
.to-figure-label {{ color: {t.MUTED}; font-size: 13px; }}
.to-figure-value {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: 28px;
    color: {t.INK};
    font-variant-numeric: tabular-nums;
}}
.to-kind {{
    color: {t.MUTED};
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
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
.to-banner {{
    border-left: 4px solid {t.ACQUIRER};
    background: {t.SURFACE};
    padding: {t.SPACING[0]}px {t.SPACING[1]}px;
    color: {t.INK};
    font-size: 14px;
}}
.to-narrow-note {{ display: none; }}
@media (max-width: 700px) {{
    .to-narrow-note {{ display: block; color: {t.MUTED}; font-size: 13px; }}
}}
</style>
"""


def inject_style() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def esc(text: object) -> str:
    """Text made safe for HTML and Markdown: escaped, and ``$`` kept from starting maths."""
    return escape(str(text)).replace("$", "&#36;")


def headline(text: str) -> None:
    """A finding headline in the serif display face (PRD 6.11)."""
    st.markdown(f'<div class="to-headline">{esc(text)}</div>', unsafe_allow_html=True)


def muted(text: str) -> None:
    st.markdown(f'<div class="to-muted">{esc(text)}</div>', unsafe_allow_html=True)


def figure_card(kind: str, label: str, value: str, explanation: str) -> None:
    """One headline figure: its kind (recurring / one-time), label, range and one-line meaning."""
    st.markdown(
        f'<div class="to-kind">{esc(kind)}</div>'
        f'<div class="to-figure-label">{esc(label)}</div>'
        f'<div class="to-figure-value">{esc(value)}</div>'
        f'<div class="to-caption">{esc(explanation)}</div>',
        unsafe_allow_html=True,
    )
