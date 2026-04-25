"""Show every formatting primitive: titles, sections, styled text,
key/value lines, receipt-style tables, barcodes, and QR codes.

Mirrors the rich first test print so we keep that look as a reference.
"""
from __future__ import annotations

from datetime import datetime

from daily_report import ReceiptPrinter, styles


def main() -> None:
    with ReceiptPrinter() as p:
        # Big title block
        styles.title(p, "MARK CHELI")
        styles.subtitle(p, "Personal Homelab")
        styles.subtitle(p, "markcheli.com")
        styles.divider_decorative(p, "=")

        # Text styles
        styles.section_header(p, "TEXT STYLES")
        p.text("- normal text\n")
        styles.styled(p, "- bold text",        bold=True)
        styles.styled(p, "- underlined",       underline=True)
        styles.styled(p, "- BIG (2x)",         big=True)
        styles.styled(p, "right-aligned",      align="right")
        styles.styled(p, "center-aligned",     align="center")

        # Key/value list
        styles.section_header(p, "KEY / VALUE")
        styles.kv_line(p, "Hostname",    "homelab")
        styles.kv_line(p, "Uptime",      "12d 4h")
        styles.kv_line(p, "Containers",  "26 / 26 up", bold_value=True)
        styles.kv_line(p, "Last deploy", "2 hours ago")

        # A fake receipt
        styles.section_header(p, "RECEIPT TABLE")
        styles.styled(p, "ORDER #1042", bold=True)
        styles.receipt_table(
            p,
            [
                ("Coffee, large",      4.50),
                ("Bagel + cream chz",  3.25),
                ("Bottled water",      2.00),
            ],
            tax_rate=0.0625,
        )

        # Barcode
        styles.section_header(p, "BARCODE")
        styles.barcode(p, "TM-M30III", kind="CODE128", height=64, width=2)

        # QR code
        styles.section_header(p, "QR CODE")
        styles.qr(p, "https://markcheli.com", size=8)

        # Footer
        p.newline()
        styles.subtitle(p, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        styles.subtitle(p, "Thanks for testing")
        p.feed(2)
        p.cut()


if __name__ == "__main__":
    main()
