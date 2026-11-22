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

/* The header strip: two rows that wrap, on a quiet surface. */
.st-key-to_header {{ background: {t.SURFACE}; }}
.st-key-to_header_row, .st-key-to_header_view, .st-key-to_header_name,
.st-key-to_header_answer {{
    row-gap: {t.SPACING[0]}px;
    column-gap: {t.SPACING[2]}px;
}}
.st-key-to_header_view {{
    border-top: {t.BORDER_WIDTH}px solid {t.BORDER};
    padding-top: {t.SPACING[0]}px;
}}
.st-key-to_header_view .to-banner {{ min-width: 16em; }}

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

/* ---- Plain-language introductions (every screen) ---- */
.to-eyebrow {{
    display: block;
    color: {t.TEAL};
    font-size: {_TY["small"]}px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}}
.to-intro {{
    font-size: {_TY["lead"]}px;
    line-height: 1.55;
    color: {t.INK};
    max-width: {t.READING_WIDTH_CH}ch;
}}
[class*="st-key-to_intro_"] {{
    background: {t.TEAL_TINT};
    border-radius: {t.CARD_RADIUS}px;
    padding: {t.SPACING[1]}px {t.SPACING[2]}px;
    margin: {t.SPACING[0]}px 0 {t.SPACING[0]}px 0;
    max-width: calc({t.READING_WIDTH_CH}ch + 22em);
}}
[class*="st-key-to_intro_"] [data-testid="stPopover"] button {{ background: {t.SURFACE}; }}
.to-body {{ font-size: {_TY["body"]}px; line-height: 1.55; color: {t.INK}; }}

/* ---- Overview hero ---- */
.st-key-to_hero {{
    background: linear-gradient(135deg, {t.SURFACE} 0%, {t.TEAL_TINT} 100%);
    border: {t.BORDER_WIDTH}px solid {t.BORDER};
    border-radius: {t.HERO_RADIUS}px;
    padding: clamp({t.SPACING[1]}px, 3vw, {t.SPACING[4]}px);
    margin-top: {t.SPACING[0]}px;
}}
.to-hero-title {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: clamp({_TY["hero_min"]}px, 1rem + 1.9vw, {_TY["hero"]}px);
    line-height: 1.16;
    color: {t.INK};
    text-wrap: balance;
    margin: {t.SPACING[0]}px 0 {t.SPACING[1]}px 0;
}}
.to-hl {{ color: {t.TEAL}; white-space: nowrap; }}
.to-hero-sub {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: clamp({_TY["lead"]}px, 0.8rem + 0.9vw, {_TY["section"] + 3}px);
    line-height: 1.3;
    color: {t.MUTED};
    margin-bottom: {t.SPACING[1]}px;
}}
.to-hero-lead {{
    font-size: {_TY["lead"]}px;
    line-height: 1.55;
    color: {t.INK};
    max-width: 62ch;
    margin-bottom: {t.SPACING[0]}px;
}}
.st-key-to_compare {{ background: {t.SURFACE}; box-shadow: 0 8px 24px rgba(22, 32, 46, 0.08); }}
.to-compare {{ padding: {t.SPACING[0]}px {t.SPACING[0] // 2}px {t.SPACING[0]}px; }}
.to-compare-row {{ margin-bottom: {t.SPACING[2]}px; }}
.to-compare-label {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: 0 {t.SPACING[0]}px;
    color: {t.MUTED};
    font-size: {_TY["muted"]}px;
    font-weight: 600;
    margin-bottom: 6px;
}}
.to-compare-label span {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-size: clamp(24px, 1rem + 1vw, {_TY["figure"]}px);
    font-variant-numeric: tabular-nums;
}}
.to-compare-naive span {{ text-decoration: line-through; text-decoration-thickness: 2px; }}
.to-compare-good {{ color: {t.TEAL}; }}
.to-track {{
    position: relative;
    height: 28px;
    border-radius: 6px;
    background: {t.PAPER};
    overflow: hidden;
}}
.to-bar {{ position: absolute; top: 0; bottom: 0; left: 0; }}
.to-bar-naive {{
    background: repeating-linear-gradient(135deg, {t.CONTROL} 0 7px, {t.BORDER} 7px 10px);
}}
.to-bar-low {{ background: {t.TEAL}; }}
.to-bar-range {{ background: {t.TEAL}; opacity: 0.4; }}
.to-bar-mark {{ position: absolute; top: 0; bottom: 0; width: 3px; background: {t.INK}; }}
.to-compare-legend {{ color: {t.MUTED}; font-size: {_TY["small"]}px; margin-top: 6px; }}
.to-compare-note {{
    color: {t.INK};
    font-size: {_TY["caption"]}px;
    line-height: 1.5;
    border-top: {t.BORDER_WIDTH}px solid {t.BORDER};
    padding-top: {t.SPACING[0]}px;
}}

/* ---- The three figures on one ledger ---- */
.st-key-to_ledger {{ background: {t.SURFACE}; }}
.st-key-to_ledger [data-testid="stColumn"] + [data-testid="stColumn"] {{
    border-left: {t.BORDER_WIDTH}px solid {t.BORDER};
    padding-left: {t.SPACING[2]}px;
}}

/* ---- Bridge steps, each with its reason ---- */
.to-steps {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 270px), 1fr));
    gap: {t.SPACING[1]}px {t.SPACING[2]}px;
    margin: {t.SPACING[0]}px 0 {t.SPACING[1]}px 0;
}}
.to-step {{ display: flex; gap: 12px; align-items: flex-start; }}
.to-step-num {{
    flex: 0 0 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: {_TY["small"]}px;
    font-weight: 600;
    color: {t.INK};
    background: {t.BORDER};
}}
.to-step-plus .to-step-num {{ background: {t.TEAL}; color: {t.SURFACE}; }}
.to-step-head {{
    display: flex;
    flex-wrap: wrap;
    gap: 2px 8px;
    align-items: baseline;
    font-weight: 600;
    font-size: {_TY["muted"]}px;
    color: {t.INK};
}}
.to-step-amt {{ color: {t.MUTED}; font-variant-numeric: tabular-nums; font-weight: 400; }}
.to-step-plus .to-step-amt {{ color: {t.TEAL}; }}
.to-step-why {{ color: {t.MUTED}; font-size: {_TY["caption"]}px; line-height: 1.45; }}

/* ---- How sure we are: tier A and B as one bar ---- */
.to-stack {{
    display: flex;
    height: 30px;
    border-radius: 6px;
    overflow: hidden;
    margin: {t.SPACING[1]}px 0 {t.SPACING[0]}px 0;
    background: {t.PAPER};
}}
.to-stack div {{
    display: flex;
    align-items: center;
    padding-left: 10px;
    font-size: {_TY["small"]}px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
}}
.to-stack-a {{ background: {t.TEAL}; color: {t.SURFACE}; }}
.to-stack-b {{ background: {t.TEAL_TINT}; color: {t.INK}; }}
.st-key-to_confidence, .st-key-to_findings {{ background: {t.SURFACE}; }}
[class*="st-key-to_finding_"] {{
    border-top: {t.BORDER_WIDTH}px solid {t.BORDER};
    padding-top: {t.SPACING[0]}px;
}}

/* ---- Explore cards ---- */
[class*="st-key-to_quad_explore_"] [data-testid="stColumn"] > div {{ height: 100%; }}
[class*="st-key-to_explore_"] {{
    background: {t.SURFACE};
    transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
}}
[class*="st-key-to_explore_"]:hover {{
    border-color: {t.TEAL} !important;
    box-shadow: 0 6px 20px rgba(15, 110, 99, 0.12);
    transform: translateY(-2px);
}}
.to-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 12px;
    margin-bottom: {t.SPACING[0]}px;
}}
.to-icon-glyph {{
    font-family: 'Material Symbols Rounded';
    font-weight: normal;
    font-style: normal;
    font-size: 26px;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    white-space: nowrap;
    font-feature-settings: 'liga';
    -webkit-font-smoothing: antialiased;
}}
.to-icon-teal {{ background: {t.TEAL_TINT}; color: {t.TEAL}; }}
.to-icon-amber {{ background: {t.SURFACE}; color: {t.AMBER}; }}
.st-key-to_explore_tour {{ background: {t.AMBER_TINT} !important; }}
.to-explore-title {{
    color: {t.MUTED};
    font-size: {_TY["small"]}px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}}
.to-explore-q {{
    font-family: '{t.FONT_SERIF}', Georgia, serif;
    font-weight: 600;
    font-size: {_TY["body"] + 2}px;
    line-height: 1.35;
    color: {t.INK};
    margin: 4px 0 {t.SPACING[0]}px 0;
}}

/* ---- Glossary (Method & limits) ---- */
.to-glossary {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
    gap: {t.SPACING[1]}px {t.SPACING[3]}px;
}}
.to-term-name {{ font-weight: 600; color: {t.INK}; font-size: {_TY["muted"]}px; }}
.to-term-text {{ color: {t.MUTED}; font-size: {_TY["caption"]}px; line-height: 1.5; }}

{_STACK} {{
    [class*="st-key-to_intro_"] {{ flex-wrap: wrap !important; }}
    .st-key-to_ledger [data-testid="stColumn"] + [data-testid="stColumn"] {{
        border-left: none;
        padding-left: 0;
        border-top: {t.BORDER_WIDTH}px solid {t.BORDER};
        padding-top: {t.SPACING[1]}px;
    }}
}}

.to-narrow-note {{ display: none; }}
{_PHONE} {{
    .to-hero-lead, .to-intro {{ font-size: {_TY["body"]}px; }}
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
    /* The bridge's eleven step names would print over each other: the numbered list of
       steps under the chart, hover and the table name them instead. */
    [class*="st-key-to_chart_main_"] .xaxislayer-above {{ display: none; }}
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


def icon_badge(name: str, tone: str = "teal") -> str:
    """HTML for a Material icon (``name`` as in ``:material/name:``) on a tinted square.

    Streamlit loads the Material Symbols Rounded face for its own icons; this uses it
    directly so the icon can sit in a styled badge. ``tone`` is ``teal`` or ``amber``.
    """
    return (
        f'<span class="to-icon to-icon-{esc(tone)}" aria-hidden="true">'
        f'<span class="to-icon-glyph">{esc(name)}</span></span>'
    )


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
