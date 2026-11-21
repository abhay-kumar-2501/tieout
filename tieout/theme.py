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

MAX_CONTENT_WIDTH = 1200
BORDER_WIDTH = 1
CARD_RADIUS = 8
STACK_BREAKPOINT = 900

ILLUSTRATIVE_LABEL = "Illustrative — synthetic data"
