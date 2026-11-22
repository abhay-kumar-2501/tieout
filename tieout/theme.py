"""Design tokens (PRD 6.11). Single source of truth for colours, fonts and spacing.

Pure constants: this module must not import streamlit so that matplotlib and
export code can use it.
"""

from __future__ import annotations

PAPER = "#FAF8F4"
SURFACE = "#FFFFFF"
INK = "#16202E"
MUTED = "#5B6676"
BORDER = "#E3DED4"
CONTROL = "#8A8478"
TEAL = "#0F6E63"
TEAL_TINT = "#E3F0EE"
AMBER = "#A64B05"
AMBER_TINT = "#FBEBD3"
RED = "#B3372F"
RED_TINT = "#F8E1DE"
ACQUIRER = "#27457A"
TARGET = "#B8642A"

COLORS: dict[str, str] = {
    "paper": PAPER,
    "surface": SURFACE,
    "ink": INK,
    "muted": MUTED,
    "border": BORDER,
    "control": CONTROL,
    "teal": TEAL,
    "teal-tint": TEAL_TINT,
    "amber": AMBER,
    "amber-tint": AMBER_TINT,
    "red": RED,
    "red-tint": RED_TINT,
    "acquirer": ACQUIRER,
    "target": TARGET,
}

FONT_SANS = "IBM Plex Sans"
FONT_SERIF = "IBM Plex Serif"
FONT_MONO = "IBM Plex Mono"

# Faces available to exports, which cannot embed fonts.
EXPORT_FONT_TITLE = "Georgia"
EXPORT_FONT_BODY = "Arial"

# 8 px spacing scale (pixels).
SPACING_UNIT = 8
SPACING: tuple[int, ...] = tuple(SPACING_UNIT * n for n in (1, 2, 3, 4, 6, 8))

# Type scale (pixels). The root size is Streamlit's ``baseFontSize``; nothing in the
# interface, charts included, is set below FONT_MIN.
BASE_FONT_SIZE = 17
FONT_MIN = 14
TYPE: dict[str, int] = {
    "hero": 44,  # the Overview's answer, serif; scales down to hero_min on a phone
    "hero_min": 28,
    "headline": 36,  # finding headline, serif; scales down to headline_min on a phone
    "headline_min": 26,
    "figure": 34,  # headline figures in cards, serif; scales down to 26 px
    "section": 23,  # section headings
    "lead": 19,  # the Overview introduction
    "body": BASE_FONT_SIZE,
    "muted": 16,  # secondary text
    "caption": 15,  # captions, chart summaries, figure labels
    "small": FONT_MIN,  # kind labels, tags, the page question
    "nav": 16,  # top navigation
}
#: Streamlit ``headingFontSizes`` (h1 to h6), in rem of BASE_FONT_SIZE.
HEADING_FONT_SIZES: tuple[str, ...] = (
    "2.25rem",
    "1.75rem",
    "1.375rem",
    "1.2rem",
    "1.0625rem",
    "1rem",
)

# Chart text (pixels): the general font, axis ticks, direct labels on marks.
CHART_FONT = 15
CHART_TICK = FONT_MIN
CHART_LABEL = FONT_MIN

# Layout. The content column is fluid: the window less a gutter that grows with the
# width (GUTTER_MIN to GUTTER_MAX), up to MAX_CONTENT_WIDTH; on very wide windows it
# takes WIDE_CONTENT_SHARE of the width, never more than ULTRAWIDE_CONTENT_WIDTH.
MAX_CONTENT_WIDTH = 1440
ULTRAWIDE_CONTENT_WIDTH = 1680
WIDE_CONTENT_SHARE = 0.66
GUTTER_MIN = 16
GUTTER_MAX = 64
READING_WIDTH_CH = 78  # longest line of running text, in characters
BORDER_WIDTH = 1
CARD_RADIUS = 8
HERO_RADIUS = 16  # the Overview's hero panel
QUAD_BREAKPOINT = 1200  # a row of four cards becomes two by two below this width
STACK_BREAKPOINT = 900  # two-column grids stack below this width
PHONE_BREAKPOINT = 700  # phone layout and the "best on a larger screen" note
TAP_TARGET = 44  # minimum height of a control on a phone

#: Chart heights by role, pixels. With the content column at its usual 1,240 to 1,440 px
#: these give the main chart about 2.4:1 to 2.8:1, other full-width charts about 2.6:1 to
#: 3:1 and charts in a two-column grid about 1.5:1; on a phone, where the grid stacks,
#: they stand a little taller than wide, which suits a portrait screen. (Streamlit sizes a
#: stretched Plotly chart once, when it mounts, so a CSS aspect ratio cannot drive the
#: height reliably.)
CHART_HEIGHTS: dict[str, int] = {
    "main": 520,  # the one full-width chart of a screen (the bridge)
    "wide": 480,  # other full-width charts
    "half": 400,  # charts in a two-column grid
}

ILLUSTRATIVE_LABEL = "Illustrative — synthetic data"
