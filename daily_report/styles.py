"""Non-data formatting: titles, sections, QR, barcodes, receipt tables.

Everything that's about *presenting* content rather than visualising data.
All functions take a ReceiptPrinter as the first argument.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .printer import ReceiptPrinter


# ---------- titles & sections ----------

def title(p: ReceiptPrinter, text: str) -> None:
    """Big centered double-size bold title."""
    p.set(align="center", bold=True, double_height=True, double_width=True)
    p.text(f"{text}\n")
    p.set(bold=False, double_height=False, double_width=False, align="left")


def subtitle(p: ReceiptPrinter, text: str) -> None:
    """Centered normal-weight subtitle."""
    p.set(align="center", bold=False)
    p.text(f"{text}\n")
    p.set(align="left")


def kicker(p: ReceiptPrinter, text: str) -> None:
    """Small uppercase label, useful above titles or KPI values."""
    p.set(align="center", bold=True)
    p.text(f"{text.upper()}\n")
    p.set(align="left", bold=False)


def section_header(p: ReceiptPrinter, text: str) -> None:
    """Whitespace, a top `=` divider, the bold title, and a bottom `=` divider.

        (blank line)
        ============================================
        TITLE
        ============================================
    """
    p.newline()
    p.divider("=")
    p.set(align="left", bold=True)
    p.text(f"{text}\n")
    p.set(bold=False)
    p.divider("=")


def divider_decorative(p: ReceiptPrinter, char: str = "*") -> None:
    """Full-width decorative divider."""
    p.divider(char, width=p.DIVIDER_WIDTH)


# ---------- raw-style text ----------

def styled(
    p: ReceiptPrinter,
    text: str,
    *,
    bold: bool = False,
    underline: bool = False,
    big: bool = False,
    align: str = "left",
) -> None:
    """Print text with style toggles, then reset to defaults."""
    p.set(
        align=align,
        bold=bold,
        underline=1 if underline else 0,
        double_height=big,
        double_width=big,
    )
    p.text(text + "\n")
    p.set(align="left", bold=False, underline=0,
          double_height=False, double_width=False)


# ---------- key/value & tables ----------

def kv_line(
    p: ReceiptPrinter,
    key: str,
    value: str,
    *,
    width: Optional[int] = None,
    bold_value: bool = False,
) -> None:
    """`key                       value` aligned to width."""
    w = width or p.CONTENT_WIDTH
    pad = max(1, w - len(key) - len(value))
    if bold_value:
        p.text(f"{key}{' ' * pad}")
        p.set(bold=True)
        p.text(f"{value}\n")
        p.set(bold=False)
    else:
        p.text(f"{key}{' ' * pad}{value}\n")


def receipt_table(
    p: ReceiptPrinter,
    items: Iterable[tuple[str, float]],
    *,
    currency: str = "$",
    tax_rate: Optional[float] = None,
    width: Optional[int] = None,
) -> None:
    """Print a list of (name, price) rows, then subtotal/tax/total.

    If tax_rate is None, only a TOTAL row is printed.
    """
    w = width or p.CONTENT_WIDTH
    items = list(items)
    p.divider("-", width=w)
    subtotal = 0.0
    for name, price in items:
        subtotal += price
        line = f"{name[:w-9]:<{w-9}}{currency}{price:>7.2f}"
        p.text(line + "\n")
    p.divider("-", width=w)
    if tax_rate is None:
        p.set(bold=True)
        p.text(f"{'TOTAL':<{w-9}}{currency}{subtotal:>7.2f}\n")
        p.set(bold=False)
    else:
        tax = round(subtotal * tax_rate, 2)
        total = subtotal + tax
        p.text(f"{'Subtotal':<{w-9}}{currency}{subtotal:>7.2f}\n")
        p.text(f"{f'Tax ({tax_rate*100:.2f}%)':<{w-9}}{currency}{tax:>7.2f}\n")
        p.set(bold=True)
        p.text(f"{'TOTAL':<{w-9}}{currency}{total:>7.2f}\n")
        p.set(bold=False)


# ---------- codes ----------

def qr(p: ReceiptPrinter, data: str, *, size: int = 8) -> None:
    """Print a centered native QR code."""
    p.set(align="center")
    p.qr(data, size=size)
    p.set(align="left")


def barcode(
    p: ReceiptPrinter,
    data: str,
    *,
    kind: str = "CODE128",
    height: int = 64,
    width: int = 2,
) -> None:
    """Print a centered barcode. CODE128 auto-prefixed with `{B` if missing."""
    p.set(align="center")
    if kind == "CODE128" and not data.startswith(("{A", "{B", "{C")):
        data = "{B" + data
    p.raw.barcode(data, kind, width=width, height=height, function_type="B")
    p.set(align="left")
