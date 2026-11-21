"""The shared stylesheet: type scale, fluid layout, cards and chart shapes (PRD 6.11).

Every size comes from ``tieout.theme``; no JavaScript. Screens opt into a layout
with keyed containers: ``st-key-to_grid_*`` (a two-column grid that stacks below
``STACK_BREAKPOINT``), ``st-key-to_cards_*`` (a row of cards that wraps) and
``st-key-to_chart_<role>_*`` (a chart drawn at its role's height, ``CHART_HEIGHTS``).
"""

from __future__ import annotations

from html import escape

import streamlit as st

from tieout import theme as t

_TY = t.TYPE
_GUTTER = f"clamp({t.GUTTER_MIN}px, 4.5vw, {t.GUTTER_MAX}px)"
_CONTENT = (
    f"min({t.ULTRAWIDE_CONTENT_WIDTH}px, max({t.MAX_CONTENT_WIDTH}px, "
    f"{t.WIDE_CONTENT_SHARE * 100:g}vw))"
)
_PHONE = f"@media (max-width: {t.PHONE_BREAKPOINT}px)"
_STACK = f"@media (max-width: {t.STACK_BREAKPOINT}px)"


_CSS = f"""
<style>
:root {{ --to-gutter: {_GUTTER}; }}

/* Fluid content column: the window less a growing gutter, capped on wide screens. */
.block-container {{
    box-sizing: border-box;
    max-width: calc({_CONTENT} + 2 * var(--to-gutter));
    padding: {t.SPACING[2] + 64}px var(--to-gutter) {t.SPACING[5] * 2}px;
}}

/* Top navigation: larger, clearer links on a quiet bar. */
[data-testid="stHeader"] {{ background: {t.PAPER}; border-bottom: 1px solid {t.BORDER}; }}
[data-testid="stTopNavLink"] {{ padding: {t.SPACING[0]}px {t.SPACING[1] - 2}px; }}
[data-testid="stTopNavLink"] p {{ font-size: {_TY["nav"]}px; }}

/* Running text keeps a readable measure however wide the column. */
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] {{
    max-width: {t.READING_WIDTH_CH}ch;
}}
/* Captions in the muted token at full opacity (Streamlit fades them below AA contrast). */
[data-testid="stCaptionContainer"] {{
    font-size: {_TY["caption"]}px;
    color: {t.MUTED};
    opacity: 1;
    line-height: 1.5;
}}
[data-testid="stWidgetLabel"] p {{ font-size: {_TY["muted"]}px; }}
[data-testid="stExpander"] summary p {{ font-size: {_TY["body"]}px; }}
[data-testid="stTooltipContent"] {{ font-size: {_TY["caption"]}px; }}

h1, h2, h3, h4 {{ color: {t.INK}; font-weight: 600; }}
.to-headline {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: clamp({_TY["headline_min"]}px, 1rem + 1.25vw, {_TY["headline"]}px);
    line-height: 1.22;
    color: {t.INK};
    max-width: 30em;
    text-wrap: balance;
    margin: {t.SPACING[0] // 2}px 0 {t.SPACING[1]}px 0;
}}
.to-question {{
    color: {t.MUTED};
    font-size: {_TY["small"]}px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: {t.SPACING[2]}px;
}}
.to-section {{
    font-family: '{t.FONT_SANS}', sans-serif;
    font-weight: 600;
    font-size: {_TY["section"]}px;
    line-height: 1.3;
    color: {t.INK};
    margin: {t.SPACING[4]}px 0 {t.SPACING[0] // 2}px 0;
}}
.to-lead {{
    font-size: {_TY["lead"]}px;
    line-height: 1.5;
    color: {t.INK};
    max-width: {t.READING_WIDTH_CH}ch;
}}
.to-muted {{
    color: {t.MUTED};
    font-size: {_TY["muted"]}px;
    line-height: 1.5;
    max-width: {t.READING_WIDTH_CH}ch;
}}
.to-caption {{ color: {t.MUTED}; font-size: {_TY["caption"]}px; line-height: 1.45; }}
.to-mono {{ font-family: '{t.FONT_MONO}', monospace; font-size: {_TY["caption"]}px; }}
.to-num {{ font-variant-numeric: tabular-nums; text-align: right; }}
.to-card {{
    background: {t.SURFACE};
    border: {t.BORDER_WIDTH}px solid {t.BORDER};
    border-radius: {t.CARD_RADIUS}px;
    padding: {t.SPACING[1]}px {t.SPACING[2]}px;
    box-shadow: none;
}}
.to-figure-label {{ color: {t.INK}; font-size: {_TY["muted"]}px; margin-top: 2px; }}
.to-figure-value {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: clamp(26px, 12px + 1.1vw, {_TY["figure"]}px);
    line-height: 1.2;
    color: {t.INK};
    font-variant-numeric: tabular-nums;
    margin: {t.SPACING[0] // 2}px 0;
}}
.to-kind {{
    color: {t.MUTED};
    font-size: {_TY["small"]}px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.to-tag {{
    display: inline-block;
    border: {t.BORDER_WIDTH}px solid {t.BORDER};
    border-radius: {t.CARD_RADIUS}px;
    padding: 3px {t.SPACING[0] + 2}px;
    background: {t.AMBER_TINT};
    color: {t.INK};
    font-size: {_TY["small"]}px;
    white-space: nowrap;
}}
.to-banner {{
    border-left: 4px solid {t.ACQUIRER};
    padding: 2px {t.SPACING[1]}px;
    color: {t.INK};
    font-size: {_TY["caption"]}px;
    line-height: 1.45;
}}
.to-range {{ font-size: {_TY["body"]}px; white-space: nowrap; }}
.to-range strong {{ font-variant-numeric: tabular-nums; }}
.to-strong {{ font-weight: 600; font-size: {_TY["body"] + 1}px; color: {t.INK}; }}

/* The header strip: one bar that wraps, and a quiet surface. */
.st-key-to_header {{ background: {t.SURFACE}; }}
.st-key-to_header_row {{ row-gap: {t.SPACING[0]}px; column-gap: {t.SPACING[2]}px; }}

/* The Overview introduction. */
.st-key-to_intro {{ background: {t.TEAL_TINT}; border-color: {t.TEAL_TINT} !important; }}

/* Cards in a row stretch to one height. */
[class*="st-key-to_cards_"] [data-testid="stColumn"] > div {{ height: 100%; }}

/* A row of four cards becomes two by two on a laptop or tablet. */
@media (max-width: {t.QUAD_BREAKPOINT}px) {{
    [class*="st-key-to_quad_"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
    [class*="st-key-to_quad_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 40% !important;  /* two to a row, whatever the gap */
        width: 40% !important;
        min-width: 40% !important;
    }}
}}

/* A two-column grid or card row stacks below the stack breakpoint. */
{_STACK} {{
    [class*="st-key-to_grid_"] [data-testid="stHorizontalBlock"],
    [class*="st-key-to_cards_"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
    [class*="st-key-to_grid_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [class*="st-key-to_cards_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }}
}}

.to-narrow-note {{ display: none; }}
{_PHONE} {{
    .to-narrow-note {{ display: block; color: {t.MUTED}; font-size: {_TY["caption"]}px; }}
    .block-container {{ padding-top: {t.SPACING[1] + 56}px; }}
    .to-section {{ margin-top: {t.SPACING[3]}px; }}
    .to-lead {{ font-size: {_TY["body"]}px; }}
    .to-question {{ margin-top: {t.SPACING[1]}px; }}
    [class*="st-key-to_quad_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }}
    /* Bar figures would overlap at this width: hover and the table give them. */
    [class*="st-key-to_chart_"] .bartext,
    [class*="st-key-to_chart_"] .textpoint,
    [class*="st-key-to_chart_main_"] .annotation {{ display: none; }}
    /* Tap targets of at least {t.TAP_TARGET} px. */
    .stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button,
    [data-testid="stPageLink"] a, [data-testid="stBaseButton-segmented_control"],
    [data-testid="stBaseButton-segmented_controlActive"], [data-baseweb="select"] > div,
    [data-testid="stExpander"] summary {{ min-height: {t.TAP_TARGET}px; }}
    .stCheckbox label, [data-testid="stCheckbox"] label {{ min-height: {t.TAP_TARGET}px;
        align-items: center; }}
}}
</style>
"""


def inject_style() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def stylesheet() -> str:
    """The stylesheet text (for tests)."""
    return _CSS


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
