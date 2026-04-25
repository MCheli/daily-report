"""Print daily reports to an Epson TM-m30III thermal receipt printer.

Public surface:
    ReceiptPrinter   - thin context-manager wrapper around python-escpos
    charts           - data-viz functions (KPI, bars, sparklines, histograms,
                       line/bar/heatmap images)
    styles           - non-data formatting (titles, sections, QR, barcodes,
                       receipt tables, decorative dividers)

Typical usage:

    from daily_report import ReceiptPrinter, charts, styles

    with ReceiptPrinter() as p:
        styles.title(p, "DAILY REPORT")
        styles.subtitle(p, "2026-04-25")
        charts.kpi_card(p, "Revenue", 12438.55, delta_pct=12.3)
        charts.horizontal_bars(p, "Sales by region", [("US", 142), ...])
        p.cut()
"""
from .printer import ReceiptPrinter
from . import charts, styles

__all__ = ["ReceiptPrinter", "charts", "styles"]
