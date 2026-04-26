"""Small CLI for ad-hoc printing and diagnostics.

Usage:
    python -m daily_report.cli status
    python -m daily_report.cli charts        # run examples/chart_sampler.py
    python -m daily_report.cli styles        # run examples/style_sampler.py
    python -m daily_report.cli kpi "Revenue" 12438.55 --delta 12.3
    python -m daily_report.cli text "hello world"
"""
from __future__ import annotations

import argparse
import importlib
import sys

from .printer import ReceiptPrinter
from . import charts, styles, report


def _cmd_status(_args: argparse.Namespace) -> None:
    s = ReceiptPrinter.status()
    for k in ("online", "cover_open", "paper_present", "error"):
        print(f"  {k:<14} {s[k]}")
    print(f"  raw            {s['raw']}")


def _cmd_kpi(args: argparse.Namespace) -> None:
    with ReceiptPrinter() as p:
        styles.title(p, "KPI")
        charts.kpi_card(
            p, args.label, args.value,
            delta_pct=args.delta, prefix=args.prefix, suffix=args.suffix,
        )
        p.feed(2)
        p.cut()


def _cmd_text(args: argparse.Namespace) -> None:
    with ReceiptPrinter() as p:
        for line in args.text:
            p.text(line + "\n")
        p.feed(2)
        p.cut()


def _cmd_qr(args: argparse.Namespace) -> None:
    with ReceiptPrinter() as p:
        styles.qr(p, args.data, size=args.size)
        p.feed(2)
        p.cut()


def _cmd_run_example(name: str) -> None:
    mod = importlib.import_module(f"examples.{name}")
    mod.main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily-report")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="query printer status")

    sp = sub.add_parser("kpi", help="print a single KPI card")
    sp.add_argument("label")
    sp.add_argument("value", type=float)
    sp.add_argument("--delta", type=float, default=None)
    sp.add_argument("--prefix", default="$")
    sp.add_argument("--suffix", default="")

    sp = sub.add_parser("text", help="print plain text lines")
    sp.add_argument("text", nargs="+")

    sp = sub.add_parser("qr", help="print a QR code")
    sp.add_argument("data")
    sp.add_argument("--size", type=int, default=8)

    sub.add_parser("charts", help="run examples/chart_sampler.py")
    sub.add_parser("styles", help="run examples/style_sampler.py")

    sp = sub.add_parser("preview", help="serve a local HTML preview at localhost:5050")
    sp.add_argument("--port", type=int, default=5050)
    sp.add_argument("--no-browser", action="store_true",
                    help="don't auto-open the browser")
    sp.add_argument("--sections", nargs="+", default=None)
    sp.add_argument("--check-urls", action="store_true")
    sp.add_argument("--github-lookback-hours", type=int, default=24 * 7)
    sp.add_argument("--stock-ticker", default="PTC")
    sp.add_argument("--weather-location", default="Ashland,MA")
    sp.add_argument("--tallied-days", type=int, default=7)

    sp = sub.add_parser("report", help="print the composed daily report")
    sp.add_argument("--sections", nargs="+", default=None)
    sp.add_argument("--check-urls", action="store_true")
    sp.add_argument("--github-lookback-hours", type=int, default=24 * 7)
    sp.add_argument("--stock-ticker", default="PTC")
    sp.add_argument("--weather-location", default="Ashland,MA")
    sp.add_argument("--tallied-days", type=int, default=7)
    sp.add_argument("--title", default="DAILY REPORT")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        _cmd_status(args)
    elif args.cmd == "kpi":
        _cmd_kpi(args)
    elif args.cmd == "text":
        _cmd_text(args)
    elif args.cmd == "qr":
        _cmd_qr(args)
    elif args.cmd == "charts":
        _cmd_run_example("chart_sampler")
    elif args.cmd == "styles":
        _cmd_run_example("style_sampler")
    elif args.cmd == "report":
        report.generate(
            args.sections,
            title=args.title,
            check_urls=args.check_urls,
            github_lookback_hours=args.github_lookback_hours,
            stock_ticker=args.stock_ticker,
            weather_location=args.weather_location,
            tallied_days=args.tallied_days,
        )
    elif args.cmd == "preview":
        from . import preview
        preview.serve(
            port=args.port,
            open_browser=not args.no_browser,
            sections=args.sections,
            check_urls=args.check_urls,
            github_lookback_hours=args.github_lookback_hours,
            stock_ticker=args.stock_ticker,
            weather_location=args.weather_location,
            tallied_days=args.tallied_days,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
