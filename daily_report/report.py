"""Compose and print the daily report.

This is the rendering layer that ties data sources to chart/style
primitives. Add a new source by:

  1. Putting it under `daily_report/sources/<name>.py` with a
     `summarize()` function that returns a dict.
  2. Adding a `_section_<name>(p)` function here that pulls from the
     source and calls into charts/styles.
  3. Registering it in `SECTIONS` below.

Run with:
    python -m daily_report.report
    python -m daily_report.report --sections homelab
    python -m daily_report.report --check-urls       # live up/down checks
"""
from __future__ import annotations

import argparse
from datetime import datetime

from . import charts, styles
from .printer import ReceiptPrinter
from .sources import homelab


# ---------- sections ----------

def _section_homelab(p: ReceiptPrinter, *, check_urls: bool = False) -> None:
    data = homelab.summarize(check_urls=check_urls)

    styles.section_header(p, "HOMELAB")
    charts.kpi_card(p, "SERVICES TRACKED", data["total"])

    # Truncate long category titles so they fit our 28-char content width.
    short = lambda s: s.split(" (")[0][:14]
    items = [(short(name), count) for name, count in data["by_category"]]
    charts.horizontal_bars(p, "By category", items)

    if check_urls and "checks" in data:
        p.newline()
        charts.kpi_card(
            p, "REACHABILITY",
            f"{data['up']}/{data['up'] + data['down']}",
            delta_pct=None,
        )
        down = [(name, "down") for name, _, ok in data["checks"] if not ok]
        if down:
            styles.section_header(p, "DOWN")
            for name, _ in down:
                styles.kv_line(p, name, "DOWN", bold_value=True)
        else:
            styles.styled(p, "All services reachable.", align="center")


SECTIONS = {
    "homelab": _section_homelab,
    # add new sections here, e.g. "github": _section_github
}


# ---------- driver ----------

def generate(
    sections: list[str] | None = None,
    *,
    check_urls: bool = False,
    title: str = "DAILY REPORT",
) -> None:
    sections = sections or list(SECTIONS.keys())
    with ReceiptPrinter() as p:
        styles.title(p, title)
        styles.subtitle(p, datetime.now().strftime("%Y-%m-%d  %H:%M"))

        for name in sections:
            fn = SECTIONS.get(name)
            if fn is None:
                styles.section_header(p, name.upper())
                p.text(f"(unknown section: {name})\n")
                continue
            try:
                if name == "homelab":
                    fn(p, check_urls=check_urls)
                else:
                    fn(p)
            except Exception as e:
                styles.section_header(p, name.upper())
                p.text(f"(failed: {e})\n")

        p.newline()
        styles.subtitle(p, "End of report")
        p.feed(2)
        p.cut()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily-report-print")
    parser.add_argument(
        "--sections", nargs="+", default=None,
        help="subset of sections to include (default: all)",
    )
    parser.add_argument(
        "--check-urls", action="store_true",
        help="do live HEAD checks against service URLs",
    )
    parser.add_argument(
        "--title", default="DAILY REPORT",
    )
    args = parser.parse_args(argv)
    generate(args.sections, check_urls=args.check_urls, title=args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
