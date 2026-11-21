"""Generate the five small guided-tour images in ``app/static/tour/`` (PRD 2.2 step 5).

Charts come from the static chart functions run on the committed demo
results; the tie-out and unit-trap pictures are drawn from the same results'
view functions. Each image is scaled to 640 px wide and reduced to a small
palette so it stays under 60 KB.

Run: ``python scripts/make_tour_images.py``
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

from tieout import theme  # noqa: E402
from tieout.export import charts  # noqa: E402
from tieout.results import Results  # noqa: E402
from tieout.views import bridge, refused_items  # noqa: E402

DEMO = ROOT / "data" / "demo" / "results"
OUT = ROOT / "app" / "static" / "tour"
WIDTH = 640
COLOURS = 64
LIMIT = 60_000

NAMES = ("bridge", "scorecard", "tieout", "resilience", "unit_trap")


def _shrink(png: bytes) -> bytes:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    height = round(image.height * WIDTH / image.width)
    image = image.resize((WIDTH, height), Image.Resampling.LANCZOS)
    image = image.quantize(COLOURS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _canvas():
    fig = Figure(figsize=(8, 4.5), dpi=200)
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 56.25)
    ax.set_axis_off()
    return fig, ax


def _png(fig: Figure) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=200, facecolor=theme.PAPER)
    return buffer.getvalue()


def _box(ax, x, y, w, h, face, edge=theme.BORDER):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5", fc=face, ec=edge, lw=1.5
        )
    )


def _arrow(ax, x1, x2, y):
    ax.add_patch(
        FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>", mutation_scale=22, color=theme.MUTED)
    )


def _text(ax, x, y, text, size, colour=theme.INK, bold=False, **kwargs):
    ax.text(
        x,
        y,
        text,
        ha="center",
        va=kwargs.pop("va", "center"),
        fontsize=size,
        color=colour,
        fontweight="bold" if bold else "normal",
        **kwargs,
    )


def _wrap(text: str, width: int) -> str:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return "\n".join([*lines, line])


def tieout_png(results: Results) -> bytes:
    """Bar, then the item it removed, then both companies' source rows."""
    frame = bridge(results, "clean")
    bar = frame[frame["kind"] == "decrease"].iloc[0]
    item = refused_items(results, int(bar["step"]), "clean").iloc[0]
    with charts._style():
        fig, ax = _canvas()
        _text(ax, 50, 51, "Click a bar. Click an item. See both source rows.", 14, bold=True)
        _box(ax, 3, 14, 27, 28, theme.AMBER_TINT)
        _text(ax, 16.5, 36, "Bridge bar", 10, theme.MUTED)
        _text(ax, 16.5, 28, _wrap(str(bar["label"]), 16), 12.5, bold=True)
        _text(ax, 16.5, 19, str(bar["text"]), 15, theme.AMBER, bold=True)
        _arrow(ax, 31, 37, 28)
        _box(ax, 38, 14, 27, 28, theme.SURFACE)
        _text(ax, 51.5, 36, "Item removed", 10, theme.MUTED)
        _text(ax, 51.5, 28, _wrap(str(item["item"]), 18), 11, bold=True)
        _text(ax, 51.5, 19, str(item["text"]), 15, theme.AMBER, bold=True)
        _arrow(ax, 66, 72, 28)
        _text(ax, 85, 37, "Source rows", 10, theme.MUTED)
        for y, name, colour in (
            (25, "Acquirer lines", theme.ACQUIRER),
            (14, "Target lines", theme.TARGET),
        ):
            _box(ax, 73, y, 24, 9, theme.SURFACE, edge=colour)
            _text(ax, 85, y + 4.5, name, 11.5, colour, bold=True)
        _text(
            ax, 50, 6, "Every number is a door, down to the rows it came from.", 11.5, theme.MUTED
        )
        return _png(fig)


def unit_trap_png(results: Results) -> bytes:
    """One real unit trap: a large price gap that is a pack size, not a saving."""
    items = refused_items(results, 1, "clean")
    pack = items[items["reason"].str.contains("looks like a pack of")].iloc[0]
    with charts._style():
        fig, ax = _canvas()
        _text(ax, 50, 51, "Not every price gap is a saving", 14, bold=True)
        _box(ax, 8, 12, 84, 32, theme.AMBER_TINT)
        _text(ax, 50, 38, str(pack["item"]), 13, bold=True)
        _text(ax, 50, 28, _wrap(str(pack["reason"]), 52), 14, theme.AMBER, bold=True)
        _text(ax, 50, 17, f"Removed from the naive figure: {pack['text']}", 11.5, theme.MUTED)
        _text(
            ax, 50, 6, "Bridge step 1 catches it before it reaches the saving.", 11.5, theme.MUTED
        )
        return _png(fig)


def render(results: Results) -> dict[str, bytes]:
    """All five images, shrunk, keyed by name."""
    return {
        "bridge": _shrink(charts.bridge_png(results, "clean")),
        "scorecard": _shrink(charts.scorecard_png(results, "clean")),
        "tieout": _shrink(tieout_png(results)),
        "resilience": _shrink(charts.concentration_png(results, "clean")),
        "unit_trap": _shrink(unit_trap_png(results)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in render(Results.load(DEMO)).items():
        if len(data) > LIMIT:
            raise SystemExit(f"{name}.png is {len(data):,} bytes, over the {LIMIT:,} limit")
        (OUT / f"{name}.png").write_bytes(data)
        print(f"{name}.png {len(data) / 1000:.0f} KB")


if __name__ == "__main__":
    main()
