"""Static chart images (PRD 7.3): matplotlib, one PNG per chart, never exported from Plotly.

Every series comes from the view functions with ``view`` passed through, so the
images show exactly the figures the screens, workbook and deck show. Figures are
drawn on ``matplotlib.figure.Figure`` objects (no pyplot, no global state) at
2x resolution (200 dpi). The palette is :mod:`tieout.theme`; entity colours are
never used for status series. Each function returns PNG bytes; given nothing to
draw it returns a labelled empty-state image rather than raising.

Fonts: the theme's IBM Plex faces ship as woff2, which matplotlib cannot load,
so images use Arial (the face the deck uses) when installed and otherwise
DejaVu Sans, which matplotlib bundles.
"""

from __future__ import annotations

import io
import math
import textwrap
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from tieout import theme
from tieout.views import (
    Unavailable,
    bridge,
    concentration,
    money_range,
    percent,
    phasing_by_quarter,
    phasing_by_year,
    prioritisation_matrix,
    scorecard_table,
    spend_pareto,
    synergy_waterfall,
    thousands,
    tornado_chart,
)

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "CHART_FUNCTIONS",
    "DPI",
    "bridge_png",
    "concentration_png",
    "pareto_png",
    "phasing_png",
    "prioritisation_png",
    "scorecard_png",
    "tornado_png",
    "waterfall_png",
]

DPI = 200
WAVE_COLOURS = {1: theme.INK, 2: theme.MUTED, 3: theme.CONTROL}
_FONT_CANDIDATES = (theme.EXPORT_FONT_BODY, "Helvetica", "DejaVu Sans")
_BASE = 11.0


@lru_cache(maxsize=1)
def _font_family() -> str:
    for name in _FONT_CANDIDATES:
        try:
            font_manager.findfont(name, fallback_to_default=False)
        except ValueError:
            continue
        return name
    return "DejaVu Sans"


@contextmanager
def _style() -> Iterator[None]:
    with matplotlib.rc_context(
        {
            "font.family": _font_family(),
            "font.size": _BASE,
            "text.color": theme.INK,
            "axes.labelcolor": theme.MUTED,
            "axes.edgecolor": theme.CONTROL,
            "xtick.color": theme.MUTED,
            "ytick.color": theme.MUTED,
            "axes.facecolor": theme.PAPER,
            "figure.facecolor": theme.PAPER,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.axisbelow": True,
            "grid.color": theme.BORDER,
            "grid.linewidth": 0.8,
            "axes.unicode_minus": True,
            "text.parse_math": False,
        }
    ):
        yield


def _figure(width: float, height: float) -> tuple[Figure, Axes]:
    fig = Figure(figsize=(width, height), dpi=DPI)
    FigureCanvasAgg(fig)
    return fig, fig.add_subplot(111)


def _png(fig: Figure) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=DPI, facecolor=theme.PAPER)
    return buffer.getvalue()


def _empty_png(message: str, width: float = 8.0, height: float = 4.5) -> bytes:
    """A labelled empty-state image."""
    with _style():
        fig, ax = _figure(width, height)
        ax.set_axis_off()
        ax.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            fontsize=_BASE + 3,
            color=theme.MUTED,
            wrap=True,
            transform=ax.transAxes,
        )
        return _png(fig)


def _usable(frame: object) -> bool:
    return isinstance(frame, pd.DataFrame) and not frame.empty


def _money_axis(ax: Axes, axis: str = "y", signed: bool = False) -> None:
    lim = ax.get_ylim() if axis == "y" else ax.get_xlim()
    biggest = max(abs(lim[0]), abs(lim[1]))
    unit, suffix = (1e6, "M") if biggest >= 2e6 else (1e3, "k")

    def fmt(value: float, _pos: int) -> str:
        scaled = value / unit
        text = (
            f"{abs(scaled):,.1f}".rstrip("0").rstrip(".")
            if suffix == "M"
            else f"{abs(scaled):,.0f}"
        )
        sign = "−" if scaled < 0 else ("+" if signed and scaled > 0 else "")
        return f"{sign}${text}{suffix}"

    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(FuncFormatter(fmt))


def _wrap(label: str, width: int) -> str:
    return textwrap.fill(label, width=width, break_long_words=False, break_on_hyphens=False)


def _clip(label: str, limit: int) -> str:
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


def _nice_floor(value: float, step: float) -> float:
    return math.floor(value / step) * step


# ---------------------------------------------------------------- floating bars


def _bar_colour(kind: str, step: int | None = None, first: bool = False) -> str:
    if kind == "decrease":
        return theme.CONTROL
    if kind == "increase":
        return theme.TEAL
    return theme.INK if first else theme.TEAL


def _draw_stacked(
    ax: Axes,
    frame: pd.DataFrame,
    wrap: int,
    bottom: float = 0.0,
    range_label: Callable[[pd.Series], str] | None = None,
) -> None:
    """Bars from ``bar_base`` with the view's own label above each, and connectors."""
    positions = np.arange(len(frame))
    top = float(np.nanmax(frame["bar_base"] + frame["bar_height"]))
    pad = (top - bottom) * 0.025
    for i, row in enumerate(frame.itertuples(index=False)):
        colour = _bar_colour(row.kind, first=i == 0)
        height = row.bar_height - max(0.0, bottom - row.bar_base)
        base = max(row.bar_base, bottom)
        ax.bar(i, height, bottom=base, width=0.62, color=colour, zorder=3)
        label = str(row.text)
        if range_label is not None and not math.isnan(row.low):
            label += "\n" + range_label(pd.Series(row._asdict()))
        ax.text(
            i,
            row.bar_base + row.bar_height + pad,
            label,
            ha="center",
            va="bottom",
            fontsize=_BASE - 1.5,
            fontweight="bold",
            color=theme.INK,
            zorder=4,
        )
        if i + 1 < len(frame):
            ax.plot(
                [i + 0.31, i + 1 - 0.31],
                [row.level, row.level],
                color=theme.MUTED,
                linewidth=0.8,
                zorder=2,
            )
    ax.set_xticks(positions)
    ax.set_xticklabels([_wrap(str(v), wrap) for v in frame["label"]], fontsize=_BASE - 2)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y")
    ax.set_xlim(-0.6, len(frame) - 0.4)


def bridge_png(results: Results, view: str | None = None) -> bytes:
    """The bridge from the naive figure to the defensible run-rate saving (PRD 6.8)."""
    frame = bridge(results, view)
    if not _usable(frame):
        return _empty_png("No bridge to show: no price gap was found.")
    with _style():
        fig, ax = _figure(10.0, 5.4)
        ax.set_ylim(0, float(frame["bar_base"].add(frame["bar_height"]).max()) * 1.18)
        _draw_stacked(
            ax,
            frame,
            wrap=12,
            range_label=lambda r: "range " + money_range(float(r["low"]), float(r["high"])),
        )
        _money_axis(ax)
        ax.set_ylabel("Annual price gap, $ (removals shown in grey)")
        fig.subplots_adjust(left=0.09, right=0.99, top=0.97, bottom=0.2)
        return _png(fig)


def waterfall_png(results: Results, view: str | None = None) -> bytes:
    """Baseline spend, less each recurring lever, to net run-rate spend (axis cut, stated)."""
    frame = synergy_waterfall(results, view)
    if not _usable(frame):
        return _empty_png("No waterfall to show: no recurring saving was found.")
    low = float(np.nanmin(frame[["level", "low"]].to_numpy(dtype=float)))
    saved = float(frame["bar_height"].iloc[1:3].sum())
    bottom = max(0.0, _nice_floor(low - 1.5 * max(saved, 1.0), 5e6 if low > 5e7 else 1e6))
    with _style():
        fig, ax = _figure(8.0, 4.8)
        top = float(frame["bar_base"].add(frame["bar_height"]).max())
        ax.set_ylim(bottom, top + (top - bottom) * 0.16)
        _draw_stacked(
            ax,
            frame,
            wrap=16,
            bottom=bottom,
            range_label=lambda r: "range " + money_range(float(r["low"]), float(r["high"])),
        )
        _money_axis(ax)
        ax.set_ylabel(f"Annual spend, $ (axis starts at {money_range(bottom, bottom)})")
        fig.subplots_adjust(left=0.13, right=0.99, top=0.97, bottom=0.14)
        return _png(fig)


# ---------------------------------------------------------------- phasing


def phasing_png(results: Results, view: str | None = None, by: str = "year") -> bytes:
    """Realised savings by wave as stacked columns, one-time costs as separate bars below."""
    quarterly = by == "quarter"
    frame = phasing_by_quarter(results, view) if quarterly else phasing_by_year(results, view)
    if not _usable(frame):
        return _empty_png("No phasing to show: no saving reaches the planning horizon.")
    if not quarterly:
        frame = frame[frame["year"] != "Total"]
    if not frame[["savings", "cost"]].abs().to_numpy().any():
        return _empty_png("No phasing to show: no saving reaches the planning horizon.")
    keys = frame["quarter"] if quarterly else frame["year"]
    names = [f"Q{int(k)}" for k in keys] if quarterly else [f"Year {int(k)}" for k in keys]
    with _style():
        fig, ax = _figure(8.0, 4.8)
        x = np.arange(len(frame))
        bottoms = np.zeros(len(frame))
        for wave in (1, 2, 3):
            values = frame[f"wave_{wave}"].to_numpy(dtype=float)
            ax.bar(
                x,
                values,
                bottom=bottoms,
                width=0.6,
                color=WAVE_COLOURS[wave],
                label=f"Wave {wave}",
                zorder=3,
            )
            bottoms += values
        costs = frame["cost"].to_numpy(dtype=float)
        ax.bar(x, costs, width=0.6, color=theme.RED, label="One-time cost", zorder=3)
        peak = float(max(bottoms.max(), 1.0))
        for xi, total, cost in zip(x, bottoms, costs, strict=True):
            if total > 0:
                ax.text(
                    xi,
                    total + peak * 0.015,
                    thousands(total),
                    ha="center",
                    va="bottom",
                    fontsize=_BASE - 1.5,
                    fontweight="bold",
                )
            if cost < 0:
                ax.text(
                    xi,
                    cost - peak * 0.015,
                    thousands(cost),
                    ha="center",
                    va="top",
                    fontsize=_BASE - 1.5,
                    fontweight="bold",
                    color=theme.RED,
                )
        ax.axhline(0, color=theme.CONTROL, linewidth=1.0, zorder=4)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.tick_params(axis="x", length=0)
        ax.grid(axis="y")
        ax.set_ylim(min(costs.min(), 0) - peak * 0.12, peak * 1.14)
        _money_axis(ax)
        ax.set_ylabel("Savings realised in the period, $")
        ax.legend(frameon=False, loc="upper left", fontsize=_BASE - 1.5, ncols=4)
        fig.subplots_adjust(left=0.13, right=0.99, top=0.97, bottom=0.1)
        return _png(fig)


# ---------------------------------------------------------------- prioritisation


def prioritisation_png(results: Results, view: str | None = None) -> bytes:
    """Saving against complexity, coloured by wave, sized by spend; the top ten labelled."""
    frame = prioritisation_matrix(results, view)
    if not _usable(frame):
        return _empty_png("No opportunities to prioritise.")
    with _style():
        fig, ax = _figure(11.0, 5.2)
        spend = frame["spend"].to_numpy(dtype=float)
        sizes = 24 + 420 * np.sqrt(spend / max(spend.max(), 1.0))
        for wave in (3, 2, 1):
            part = frame["wave"] == wave
            if part.any():
                ax.scatter(
                    frame.loc[part, "complexity"],
                    frame.loc[part, "base"],
                    s=sizes[part.to_numpy()],
                    color=WAVE_COLOURS[wave],
                    alpha=0.72,
                    edgecolors=theme.PAPER,
                    linewidths=0.8,
                    label=f"Wave {wave}",
                    zorder=3,
                )
        ax.grid(True)
        ax.set_xlabel("Complexity (1 = easy, 5 = hard)")
        ax.set_ylabel("Base-case annual saving, $")
        _money_axis(ax)
        xs = frame["complexity"].to_numpy(dtype=float)
        ax.set_xlim(max(0.8, xs.min() - 0.3), xs.max() + 0.6)
        top = float(frame["base"].max())
        ax.set_ylim(-top * 0.04, top * 1.12)
        legend = ax.legend(
            frameon=False, loc="upper right", fontsize=_BASE - 1.5, ncols=3, markerscale=0.5
        )
        for handle in legend.legend_handles:
            handle.set_sizes([60])
        fig.subplots_adjust(left=0.09, right=0.66, top=0.97, bottom=0.12)
        labelled = frame[frame["show_label"]]
        fig.text(0.69, 0.965, "Ten largest, by saving", fontsize=_BASE, fontweight="bold", va="top")
        step = 0.088
        for n, r in enumerate(labelled.itertuples(index=False), start=1):
            ax.annotate(
                str(n),
                (float(r.complexity), float(r.base)),
                xytext=(0, 0),
                textcoords="offset points",
                ha="center",
                va="center",
                fontsize=_BASE - 2,
                fontweight="bold",
                color=theme.INK,
                zorder=6,
                bbox={"boxstyle": "circle,pad=0.18", "fc": theme.PAPER, "ec": theme.INK, "lw": 0.8},
            )
            name = _wrap(_clip(str(r.label), 56), 34).replace("\n", "\n    ")
            fig.text(
                0.69,
                0.9 - (n - 1) * step,
                f"{n}  W{int(r.wave)}  {thousands(float(r.base))}\n    {name}",
                fontsize=_BASE - 2.5,
                va="top",
                linespacing=1.25,
            )
        return _png(fig)


# ---------------------------------------------------------------- scorecard


def _target_text(target: object, passed: object) -> str:
    """``>= 0.98`` as ``target ≥ 98.0%, met``."""
    operator, _, bound = str(target).partition(" ")
    sign = {">=": "≥", "<=": "≤"}.get(operator, operator)
    state = "met" if passed else "missed"
    return f"target {sign} {percent(float(bound))}, {state}"


def scorecard_png(results: Results, view: str | None = None) -> bytes:
    """Held-out accuracy, the tool against the naive baseline (demo data only)."""
    card = scorecard_table(results, view)
    if isinstance(card, Unavailable) or not _usable(card):
        reason = card.message if isinstance(card, Unavailable) and card.message else ""
        return _empty_png(reason or "No accuracy scorecard for this run (demo data only).")
    rows = card.iloc[::-1].reset_index(drop=True)
    with _style():
        fig, ax = _figure(8.0, 4.8)
        y = np.arange(len(rows))
        tool = rows["tool"].astype(float).fillna(0.0).to_numpy()
        base = rows["baseline"].astype(float).fillna(0.0).to_numpy()
        ax.barh(y + 0.19, tool, height=0.34, color=theme.TEAL, label="Tie-Out", zorder=3)
        ax.barh(y - 0.19, base, height=0.34, color=theme.CONTROL, label="Naive baseline", zorder=3)
        for yi, t, b in zip(y, tool, base, strict=True):
            ax.text(
                t + 0.012, yi + 0.19, percent(t), va="center", fontsize=_BASE - 2, fontweight="bold"
            )
            ax.text(
                b + 0.012, yi - 0.19, percent(b), va="center", fontsize=_BASE - 2, color=theme.MUTED
            )
        ax.set_yticks(y)
        ax.set_yticklabels(
            [
                f"{label}\n{_target_text(target, passed)}" if target else str(label)
                for label, target, passed in zip(
                    rows["label"], rows["target"], rows["passed"], strict=True
                )
            ],
            fontsize=_BASE - 1.5,
        )
        ax.set_xlim(0, 1.15)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0%}"))
        ax.grid(axis="x")
        ax.tick_params(axis="y", length=0)
        ax.set_xlabel("Held-out seed, share of the planted truth")
        ax.legend(
            frameon=False,
            loc="lower left",
            bbox_to_anchor=(0, 1.0),
            ncols=2,
            fontsize=_BASE - 1.5,
        )
        fig.subplots_adjust(left=0.27, right=0.99, top=0.92, bottom=0.12)
        return _png(fig)


# ---------------------------------------------------------------- tornado


def tornado_png(results: Results, view: str | None = None) -> bytes:
    """Effect of each assumption on the base run-rate saving, sorted by size."""
    frame = tornado_chart(results, view)
    if not _usable(frame):
        return _empty_png("No assumptions to test.")
    rows = frame.iloc[::-1].reset_index(drop=True)
    with _style():
        fig, ax = _figure(8.0, 5.0)
        y = np.arange(len(rows))
        low = rows["effect_low"].to_numpy(dtype=float)
        high = rows["effect_high"].to_numpy(dtype=float)
        ax.barh(
            y, low, height=0.6, color=theme.MUTED, label="Assumption at its low value", zorder=3
        )
        ax.barh(
            y, high, height=0.6, color=theme.TEAL, label="Assumption at its high value", zorder=3
        )
        span = float(max(np.abs(low).max(), np.abs(high).max(), 1.0))
        for yi, lo, hi in zip(y, low, high, strict=True):
            for value in (lo, hi):
                sign = "+" if value > 0 else ""
                ax.text(
                    value + (span * 0.015 if value >= 0 else -span * 0.015),
                    yi,
                    sign + thousands(value),
                    va="center",
                    ha="left" if value >= 0 else "right",
                    fontsize=_BASE - 2.5,
                )
        ax.axvline(0, color=theme.INK, linewidth=1.0, zorder=4)
        ax.set_yticks(y)
        ax.set_yticklabels([_clip(str(v), 34) for v in rows["label"]], fontsize=_BASE - 1.5)
        ax.tick_params(axis="y", length=0)
        ax.set_xlim(-span * 1.35, span * 1.35)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        _money_axis(ax, axis="x", signed=True)
        ax.grid(axis="x")
        ax.set_xlabel("Change in base run-rate saving, $")
        ax.legend(frameon=False, loc="lower right", fontsize=_BASE - 2)
        fig.subplots_adjust(left=0.33, right=0.99, top=0.97, bottom=0.13)
        return _png(fig)


# ---------------------------------------------------------------- Pareto


def pareto_png(results: Results, view: str | None = None) -> bytes:
    """Vendor fragmentation: spend by rank with cumulative share, before and after matching."""
    data = spend_pareto(results, view)
    panels = [
        (
            "Vendor records, before matching",
            data["before"],
            theme.CONTROL,
            data["vendors_to_share"]["before"],
        ),
        (
            "Parent vendors, after matching",
            data["after"],
            theme.TEAL,
            data["vendors_to_share"]["after"],
        ),
    ]
    if not all(_usable(p[1]) for p in panels):
        return _empty_png("No vendor spend to show.", 9.0, 4.2)
    with _style():
        fig = Figure(figsize=(9.0, 4.4), dpi=DPI)
        FigureCanvasAgg(fig)
        axes = fig.subplots(1, 2, sharey=False)
        for ax, (title, frame, colour, reach) in zip(axes, panels, strict=True):
            ranks = frame["rank"].to_numpy()
            ax.bar(ranks, frame["spend"].to_numpy(dtype=float), width=1.0, color=colour, zorder=3)
            ax.set_title(title, loc="left", fontsize=_BASE, color=theme.INK, fontweight="bold")
            ax.set_xlabel("Vendors, largest first")
            ax.set_xlim(0, len(frame) + 1)
            _money_axis(ax)
            twin = ax.twinx()
            twin.plot(ranks, frame["cumulative_share"], color=theme.INK, linewidth=1.6, zorder=4)
            twin.axhline(data["share"], color=theme.MUTED, linestyle="--", linewidth=1.0)
            twin.axvline(reach, color=theme.MUTED, linestyle="--", linewidth=1.0)
            twin.set_ylim(0, 1.05)
            twin.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0%}"))
            twin.spines["right"].set_visible(True)
            twin.spines["right"].set_color(theme.CONTROL)
            twin.text(
                min(reach + len(frame) * 0.03, len(frame) * 0.98),
                0.5,
                f"{reach:,} vendors\nreach {data['share']:.0%}",
                fontsize=_BASE - 1.5,
                fontweight="bold",
                ha="left" if reach < len(frame) * 0.6 else "right",
            )
            ax.grid(axis="y")
        axes[0].set_ylabel("Spend per vendor, $")
        fig.subplots_adjust(left=0.08, right=0.94, top=0.9, bottom=0.14, wspace=0.42)
        return _png(fig)


# ---------------------------------------------------------------- concentration


def concentration_png(results: Results, view: str | None = None) -> bytes:
    """The largest vendor's share per category, before and after, against the cap."""
    data = concentration(results, view)
    vendors, categories = data["vendors"], data["categories"]
    if not _usable(vendors) or not _usable(categories):
        return _empty_png("No concentration to show.")
    limited = categories[categories["cap_limits"]].head(8)
    chosen = limited if not limited.empty else categories.head(8)
    top = (
        vendors[vendors["vendor"] != "All other vendors"]
        .sort_values(["category", "share_after"], ascending=[True, False])
        .drop_duplicates("category")
        .set_index("category")
    )
    rows = [(c, top.loc[c]) for c in chosen["category"] if c in top.index][::-1]
    if not rows:
        return _empty_png("No concentration to show.")
    with _style():
        fig, ax = _figure(8.0, 4.8)
        y = np.arange(len(rows))
        ax.barh(
            y + 0.19,
            [r["share_before"] for _, r in rows],
            height=0.34,
            color=theme.CONTROL,
            label="Largest vendor's share before",
            zorder=3,
        )
        ax.barh(
            y - 0.19,
            [r["share_after"] for _, r in rows],
            height=0.34,
            color=theme.TEAL,
            label="Largest vendor's share after",
            zorder=3,
        )
        for yi, (_, r) in zip(y, rows, strict=True):
            cap = r["cap"]
            if not (isinstance(cap, float) and math.isnan(cap)):
                ax.plot([cap, cap], [yi - 0.4, yi + 0.4], color=theme.RED, linewidth=2.0, zorder=5)
        ax.plot([], [], color=theme.RED, linewidth=2.0, label="Concentration cap")
        ax.set_yticks(y)
        ax.set_yticklabels([_clip(str(c), 30) for c, _ in rows], fontsize=_BASE - 1.5)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0%}"))
        ax.set_xlim(0, 1.0)
        ax.grid(axis="x")
        ax.tick_params(axis="y", length=0)
        ax.set_xlabel("Share of the category's spend")
        ax.legend(
            frameon=False,
            loc="lower left",
            bbox_to_anchor=(-0.45, 1.0),
            ncols=3,
            fontsize=_BASE - 2,
        )
        fig.subplots_adjust(left=0.34, right=0.96, top=0.9, bottom=0.13)
        return _png(fig)


CHART_FUNCTIONS: dict[str, Callable[..., bytes]] = {
    "bridge": bridge_png,
    "waterfall": waterfall_png,
    "phasing": phasing_png,
    "prioritisation": prioritisation_png,
    "scorecard": scorecard_png,
    "tornado": tornado_png,
    "pareto": pareto_png,
    "concentration": concentration_png,
}
