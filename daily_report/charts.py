"""Data visualizations sized for an 80mm thermal receipt.

All functions take a ReceiptPrinter as the first argument.

Two flavours of chart:

  Text-based (fast, paper-cheap, "native" feel):
    kpi_card, horizontal_bars, leaderboard, progress, histogram, stacked_100

  Image-based (slower, more paper, richer):
    sparkline, line_chart, bar_chart, heatmap

Default widths come from ReceiptPrinter constants (BAR_WIDTH=12,
CONTENT_WIDTH=28, IMAGE_WIDTH_PX=512). Override per call if needed.
"""
from __future__ import annotations

import io
from typing import Iterable, Optional, Sequence

from PIL import Image, ImageDraw

from .printer import ReceiptPrinter


# ---------- shared helpers ----------

def _bar(value: float, max_value: float, width: int, char: str = "#") -> str:
    if max_value <= 0:
        return "." * width
    n = int(round(width * value / max_value))
    n = max(0, min(width, n))
    return char * n + "." * (width - n)


def _mpl_to_image(fig, width_px: int) -> Image.Image:
    """Render a matplotlib figure to a 1-bit PIL image at the given width."""
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=150, bbox_inches="tight",
        facecolor="white", edgecolor="white",
    )
    import matplotlib.pyplot as plt
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("L")
    w, h = img.size
    new_h = int(h * width_px / w)
    img = img.resize((width_px, new_h), Image.LANCZOS)
    return img.point(lambda v: 0 if v < 160 else 255, mode="1")


# ---------- text charts ----------

def kpi_card(
    p: ReceiptPrinter,
    label: str,
    value: str | float,
    *,
    delta_pct: Optional[float] = None,
    prefix: str = "",
    suffix: str = "",
) -> None:
    """A centered "stat card": small label, big bold value, optional delta.

    Intentionally compact - no surrounding `****` dividers since the
    section_header above already provides visual separation.
    """
    p.set(align="center")
    p.text(f"{label}\n")
    p.set(bold=True, double_height=True, double_width=True)
    if isinstance(value, bool):
        p.text(f"{prefix}{value}{suffix}\n")
    elif isinstance(value, int):
        p.text(f"{prefix}{value:,}{suffix}\n")
    elif isinstance(value, float):
        p.text(f"{prefix}{value:,.2f}{suffix}\n")
    else:
        p.text(f"{prefix}{value}{suffix}\n")
    p.set(bold=False, double_height=False, double_width=False)
    if delta_pct is not None:
        arrow = "^" if delta_pct >= 0 else "v"
        p.text(f"{arrow} {delta_pct:+.1f}% vs last week\n")
    p.set(align="left")


def horizontal_bars(
    p: ReceiptPrinter,
    title: str,
    items: Sequence[tuple[str, float]],
    *,
    bar_width: Optional[int] = None,
    name_width: int = 6,
    value_width: int = 5,
) -> None:
    """Horizontal bar chart from (name, value) tuples.

    Default layout: name(6) + bar(12) + space + value(5) = 24 chars.
    """
    bw = bar_width or p.BAR_WIDTH
    p.set(bold=True); p.text(f"{title}\n"); p.set(bold=False)
    p.newline()
    if not items:
        return
    mx = max(v for _, v in items)
    for name, v in items:
        p.text(f"{name[:name_width]:<{name_width}}"
               f"{_bar(v, mx, bw)} "
               f"{v:>{value_width}}\n")


def leaderboard(
    p: ReceiptPrinter,
    title: str,
    items: Sequence[tuple[str, float]],
    *,
    bar_width: int = 8,
    name_width: int = 12,
    value_fmt: str = "${:>6,.0f}",
) -> None:
    """Single-line ranked list: rank, name, value, inline bar."""
    p.set(bold=True); p.text(f"{title}\n"); p.set(bold=False)
    p.newline()
    if not items:
        return
    mx = max(v for _, v in items)
    for i, (name, v) in enumerate(items, 1):
        n = int(round(bar_width * v / mx)) if mx > 0 else 0
        bar_str = "#" * n + "." * (bar_width - n)
        p.text(f"{i:>2}. {name[:name_width]:<{name_width}}"
               f"{value_fmt.format(v)} {bar_str}\n")


def progress(
    p: ReceiptPrinter,
    title: str,
    goals: Sequence[tuple[str, float]],
    *,
    bar_width: int = 12,
) -> None:
    """`[####------]  62%  Q2 revenue` rows. Fractions are 0..1."""
    p.set(bold=True); p.text(f"{title}\n"); p.set(bold=False)
    p.newline()
    for name, frac in goals:
        frac = max(0.0, min(1.0, frac))
        pct = int(round(frac * 100))
        filled = int(round(bar_width * frac))
        bar = "[" + "#" * filled + "-" * (bar_width - filled) + "]"
        p.text(f"{bar} {pct:>3}% {name}\n")


def histogram(
    p: ReceiptPrinter,
    title: str,
    labels: Sequence[str],
    counts: Sequence[int],
    *,
    bar_width: Optional[int] = None,
    label_width: int = 4,
    count_width: int = 4,
) -> None:
    """Pre-binned histogram. Caller provides labels and counts."""
    bw = bar_width or p.BAR_WIDTH
    p.set(bold=True); p.text(f"{title}\n"); p.set(bold=False)
    p.newline()
    if not counts:
        return
    mx = max(counts)
    for label, c in zip(labels, counts):
        p.text(f"{label:<{label_width}} {_bar(c, mx, bw)} {c:>{count_width}}\n")


def stacked_100(
    p: ReceiptPrinter,
    title: str,
    parts: Sequence[tuple[str, float]],
    *,
    chars: str = "#=*.+",
    width: Optional[int] = None,
) -> None:
    """100% stacked bar with a character legend. parts = [(label, value), ...]."""
    w = width or p.DIVIDER_WIDTH
    p.set(bold=True); p.text(f"{title}\n"); p.set(bold=False)
    p.newline()
    total = sum(v for _, v in parts) or 1
    line = ""
    for (_, v), ch in zip(parts, chars):
        line += ch * int(round(w * v / total))
    p.text(line[:w] + "\n")
    p.newline()
    for (name, v), ch in zip(parts, chars):
        pct = round(100 * v / total)
        p.text(f"  {ch}  {name:<12}{pct:>3}%\n")


# ---------- image charts ----------

def sparkline(
    p: ReceiptPrinter,
    name: str,
    values: Sequence[float],
    *,
    height_px: int = 40,
    width_px: Optional[int] = None,
) -> None:
    """Single-metric sparkline rendered as a small image."""
    w = width_px or p.IMAGE_WIDTH_PX
    if values:
        last = values[-1]
        delta = values[-1] - values[0]
        p.text(f"{name:<12} now={last:<5.0f} d={delta:+.0f}\n")
        img = _sparkline_image(values, w, height_px)
        p.image(img)
        p.newline()


def _sparkline_image(values: Sequence[float], w: int, h: int) -> Image.Image:
    img = Image.new("1", (w, h), 1)
    d = ImageDraw.Draw(img)
    lo, hi = min(values), max(values)
    span = hi - lo if hi > lo else 1
    pts = [
        (
            int(i * (w - 1) / max(1, len(values) - 1)),
            int(h - 1 - (v - lo) / span * (h - 1)),
        )
        for i, v in enumerate(values)
    ]
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=0, width=2)
    return img


def line_chart(
    p: ReceiptPrinter,
    title: str,
    x: Sequence[float],
    y: Sequence[float],
    *,
    xlabel: str = "",
    ylabel: str = "",
    fill: bool = True,
    width_px: Optional[int] = None,
) -> None:
    """matplotlib line chart, optionally with shaded area under the curve."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 2.5))
    ax.plot(x, y, color="black", linewidth=2.2)
    if fill and y:
        ax.fill_between(x, y, min(y) - 1, color="black", alpha=0.12)
    ax.set_title(title, fontsize=12, fontweight="bold")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    p.image(_mpl_to_image(fig, width_px or p.IMAGE_WIDTH_PX))


def bar_chart(
    p: ReceiptPrinter,
    title: str,
    cats: Sequence[str],
    vals: Sequence[float],
    *,
    width_px: Optional[int] = None,
    annotate: bool = True,
) -> None:
    """matplotlib bar chart with optional value labels above each bar."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 2.5))
    ax.bar(cats, vals, color="black", edgecolor="black")
    if annotate:
        for i, v in enumerate(vals):
            ax.text(i, v + max(vals) * 0.02, f"{v:g}",
                    ha="center", fontsize=10, fontweight="bold")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if vals:
        ax.set_ylim(0, max(vals) * 1.18)
    p.image(_mpl_to_image(fig, width_px or p.IMAGE_WIDTH_PX))


def heatmap(
    p: ReceiptPrinter,
    title: str,
    matrix,
    *,
    row_labels: Optional[Sequence[str]] = None,
    col_label_positions: Optional[Sequence[tuple[int, str]]] = None,
    width_px: Optional[int] = None,
    aspect: str = "equal",
) -> None:
    """matplotlib imshow heatmap. Good for calendar-style activity grids.

    `matrix` is a 2D array-like (numpy.ndarray works).
    `col_label_positions` is [(col_index, label), ...] for sparse x-tick labels.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.5, 1.8))
    ax.imshow(matrix, cmap="Greys", aspect=aspect)
    if row_labels:
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=8)
    if col_label_positions:
        ax.set_xticks([i for i, _ in col_label_positions])
        ax.set_xticklabels([s for _, s in col_label_positions], fontsize=8)
    ax.set_title(title, fontsize=12, fontweight="bold")
    for s in ax.spines.values():
        s.set_visible(False)
    p.image(_mpl_to_image(fig, width_px or p.IMAGE_WIDTH_PX))
